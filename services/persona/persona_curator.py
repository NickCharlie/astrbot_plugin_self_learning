"""
Persona prompt curation service.

Inspired by the ACE (Agentic Context Engineering) Curator pattern, this
service periodically analyses and restructures persona prompts to prevent
unbounded growth caused by append-only incremental updates.

The Curator executes four operation types on prompt sections:
    KEEP   - Retain the section as-is.
    MERGE  - Combine two or more semantically overlapping sections.
    UPDATE - Rewrite a section to be more concise while preserving intent.
    DELETE - Remove an obsolete or contradictory section.

Design principles:
    - Section-count trigger: curation fires after N incremental append
      sections accumulate (default 5), rather than a fixed token budget.
    - Token budget target: once triggered, the LLM is instructed to
      compress the prompt down to a configurable token limit.
    - Safety validation: a consistency check rejects curations that
      would alter the core personality beyond an acceptable threshold.
    - LLM-driven: the actual merge/rewrite decisions are delegated to
      the LLM via FrameworkLLMAdapter, keeping the curator logic
      declarative and testable.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ...config import PluginConfig
from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...utils.guardrails_manager import get_guardrails_manager


# Section header pattern used by PersonaManagerUpdater.
_INCREMENTAL_RE = re.compile(
    r"【增量更新\s*-\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)】"
)
_GROUP_HEADER_RE = re.compile(r"【群组专用版本\s*-\s*群组ID:\s*(.+?)】")
# Markdown-style section headers produced by MLAnalyzer conservative merge.
_ENHANCEMENT_RE = re.compile(r"^##\s+学习增强特征\s*:", re.MULTILINE)

# Rough token estimation: 1 CJK char ~ 1.5 tokens, 1 ASCII word ~ 1 token.
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _estimate_tokens(text: str) -> int:
    """Estimate token count for mixed CJK/ASCII text."""
    if not text:
        return 0
    cjk_chars = len(_CJK_RANGE.findall(text))
    ascii_words = len(re.findall(r"[a-zA-Z0-9]+", text))
    return int(cjk_chars * 1.5 + ascii_words + len(text) * 0.05)


@dataclass
class PromptSection:
    """A parsed section of the persona prompt."""

    section_id: str
    content: str
    section_type: str  # "base" | "incremental" | "group_header"
    timestamp: Optional[str] = None


@dataclass
class CurationOperation:
    """A single curation operation proposed by the LLM."""

    op_type: str  # "KEEP" | "MERGE" | "UPDATE" | "DELETE"
    target_ids: List[str] = field(default_factory=list)
    new_content: str = ""
    reason: str = ""


@dataclass
class CurationResult:
    """Outcome of a curation pass."""

    success: bool
    original_token_count: int = 0
    curated_token_count: int = 0
    operations: List[CurationOperation] = field(default_factory=list)
    curated_prompt: str = ""


class PersonaCurator:
    """Persona prompt curation service.

    Usage::

        curator = PersonaCurator(config, llm_adapter)
        result = await curator.curate(group_id, current_prompt)
        if result.success:
            # Apply result.curated_prompt via PersonaManagerUpdater
            ...
    """

    def __init__(
        self,
        config: PluginConfig,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
    ) -> None:
        self._config = config
        self._llm = llm_adapter
        self._token_budget = getattr(
            config, "persona_prompt_token_budget", 4000
        )
        self._min_sections = getattr(
            config, "persona_curation_min_sections", 5
        )

    # Public API

    async def curate(
        self,
        group_id: str,
        current_prompt: str,
        token_budget: Optional[int] = None,
    ) -> CurationResult:
        """Execute a curation pass on the given persona prompt.

        Args:
            group_id: Identifier of the chat group.
            current_prompt: The full current persona system prompt.
            token_budget: Override the configured token budget.

        Returns:
            A ``CurationResult`` describing what was done.
        """
        budget = token_budget if token_budget is not None else self._token_budget
        original_tokens = _estimate_tokens(current_prompt)

        sections = self._parse_prompt_sections(current_prompt)

        incremental_sections = [
            s for s in sections if s.section_type == "incremental"
        ]
        if len(incremental_sections) < self._min_sections:
            logger.debug(
                f"[PersonaCurator] Only {len(incremental_sections)} "
                f"incremental sections for group {group_id}, "
                f"skipping curation (min={self._min_sections})"
            )
            return CurationResult(
                success=True,
                original_token_count=original_tokens,
                curated_token_count=original_tokens,
                curated_prompt=current_prompt,
            )

        # Request LLM-driven curation.
        operations = await self._request_curation(
            sections, budget, group_id
        )

        if not operations:
            return CurationResult(
                success=False,
                original_token_count=original_tokens,
                curated_token_count=original_tokens,
                curated_prompt=current_prompt,
            )

        curated = self._apply_operations(sections, operations)
        curated_tokens = _estimate_tokens(curated)

        # Validate: the base persona section must still be present.
        base_sections = [
            s for s in sections if s.section_type == "base"
        ]
        if base_sections:
            base_content = base_sections[0].content
            if base_content.strip() and base_content.strip() not in curated:
                logger.warning(
                    "[PersonaCurator] Curation would remove base persona "
                    "content. Rejecting result."
                )
                return CurationResult(
                    success=False,
                    original_token_count=original_tokens,
                    curated_token_count=original_tokens,
                    curated_prompt=current_prompt,
                )

        logger.info(
            f"[PersonaCurator] Curation complete for group {group_id}: "
            f"{original_tokens} -> {curated_tokens} tokens "
            f"({len(operations)} operations)"
        )

        return CurationResult(
            success=True,
            original_token_count=original_tokens,
            curated_token_count=curated_tokens,
            operations=operations,
            curated_prompt=curated,
        )

    def should_curate(self, current_prompt: str) -> bool:
        """Check whether the prompt has accumulated enough incremental sections.

        Triggers curation when the number of incremental/enhancement sections
        reaches ``persona_curation_min_sections`` (default 5).
        """
        sections = self._parse_prompt_sections(current_prompt)
        incremental_count = sum(
            1 for s in sections if s.section_type == "incremental"
        )
        return incremental_count >= self._min_sections

    # Parsing

    def _parse_prompt_sections(
        self, prompt: str
    ) -> List[PromptSection]:
        """Split a persona prompt into structural sections.

        Recognises:
        - Base section: everything before the first incremental marker.
        - Group header: the group-specific version marker.
        - Incremental sections: ``【增量更新 - TIMESTAMP】`` blocks.
        - Enhancement sections: ``## 学习增强特征:`` blocks produced by
          MLAnalyzer conservative prompt merge.
        """
        sections: List[PromptSection] = []
        lines = prompt.split("\n")
        current_lines: List[str] = []
        current_type = "base"
        current_id = "base"
        current_ts: Optional[str] = None
        section_counter = 0

        for line in lines:
            inc_match = _INCREMENTAL_RE.search(line)
            grp_match = _GROUP_HEADER_RE.search(line)
            enh_match = _ENHANCEMENT_RE.search(line)

            if inc_match:
                # Flush previous section.
                if current_lines:
                    sections.append(PromptSection(
                        section_id=current_id,
                        content="\n".join(current_lines).strip(),
                        section_type=current_type,
                        timestamp=current_ts,
                    ))
                section_counter += 1
                current_type = "incremental"
                current_id = f"inc_{section_counter}"
                current_ts = inc_match.group(1)
                current_lines = [line]

            elif grp_match:
                if current_lines:
                    sections.append(PromptSection(
                        section_id=current_id,
                        content="\n".join(current_lines).strip(),
                        section_type=current_type,
                        timestamp=current_ts,
                    ))
                current_type = "group_header"
                current_id = "group_header"
                current_ts = None
                current_lines = [line]

            elif enh_match:
                # ``## 学习增强特征:`` block from MLAnalyzer.
                if current_lines:
                    sections.append(PromptSection(
                        section_id=current_id,
                        content="\n".join(current_lines).strip(),
                        section_type=current_type,
                        timestamp=current_ts,
                    ))
                section_counter += 1
                current_type = "incremental"
                current_id = f"enh_{section_counter}"
                current_ts = None
                current_lines = [line]

            else:
                current_lines.append(line)

        # Flush trailing section.
        if current_lines:
            sections.append(PromptSection(
                section_id=current_id,
                content="\n".join(current_lines).strip(),
                section_type=current_type,
                timestamp=current_ts,
            ))

        return [s for s in sections if s.content]

    # LLM interaction

    async def _request_curation(
        self,
        sections: List[PromptSection],
        token_budget: int,
        group_id: str,
    ) -> List[CurationOperation]:
        """Ask the LLM to propose curation operations."""
        if not self._llm:
            logger.warning(
                "[PersonaCurator] No LLM adapter available, "
                "falling back to simple truncation"
            )
            return self._fallback_truncation(sections, token_budget)

        # Build the prompt for the LLM.
        sections_desc = []
        for s in sections:
            token_est = _estimate_tokens(s.content)
            sections_desc.append(
                f"[{s.section_id}] type={s.section_type} "
                f"tokens~{token_est} "
                f"timestamp={s.timestamp or 'N/A'}\n"
                f"---\n{s.content}\n---"
            )

        prompt = (
            "You are a persona prompt curator. The following persona prompt "
            "has grown too large and needs to be compressed.\n\n"
            f"Current total tokens: ~{sum(_estimate_tokens(s.content) for s in sections)}\n"
            f"Target token budget: {token_budget}\n\n"
            "Sections:\n" + "\n\n".join(sections_desc) + "\n\n"
            "Rules:\n"
            "1. NEVER modify or delete the 'base' section.\n"
            "2. MERGE semantically overlapping incremental sections.\n"
            "3. DELETE outdated or contradictory incremental sections.\n"
            "4. UPDATE verbose sections to be more concise.\n"
            "5. KEEP sections that are unique and valuable.\n\n"
            "Return a JSON array of operations:\n"
            '[{"op": "KEEP|MERGE|UPDATE|DELETE", '
            '"target_ids": ["id1", ...], '
            '"new_content": "merged/updated text (empty for KEEP/DELETE)", '
            '"reason": "brief explanation"}]'
        )

        try:
            response = await self._llm.filter_chat_completion(prompt=prompt)
            if not response:
                return self._fallback_truncation(sections, token_budget)

            gm = get_guardrails_manager()
            parsed = gm.parse_curation_operations(response)
            if parsed is None:
                logger.warning(
                    "[PersonaCurator] Guardrails failed to parse curation "
                    "response"
                )
                return self._fallback_truncation(sections, token_budget)

            operations = []
            for item in parsed.operations:
                operations.append(CurationOperation(
                    op_type=item.op,
                    target_ids=item.target_ids,
                    new_content=item.new_content,
                    reason=item.reason,
                ))
            return operations

        except Exception as exc:
            logger.warning(
                f"[PersonaCurator] LLM curation request failed: {exc}"
            )
            return self._fallback_truncation(sections, token_budget)

    def _fallback_truncation(
        self,
        sections: List[PromptSection],
        token_budget: int,
    ) -> List[CurationOperation]:
        """Simple fallback: keep base + most recent incremental sections.

        Used when LLM is unavailable or returns invalid output.
        """
        operations: List[CurationOperation] = []
        incremental = [
            s for s in sections if s.section_type == "incremental"
        ]

        # Sort by timestamp descending; delete oldest first.
        incremental.sort(key=lambda s: s.timestamp or "", reverse=True)

        total = sum(_estimate_tokens(s.content) for s in sections)
        idx = len(incremental) - 1

        while total > token_budget and idx >= 0:
            section = incremental[idx]
            total -= _estimate_tokens(section.content)
            operations.append(CurationOperation(
                op_type="DELETE",
                target_ids=[section.section_id],
                reason="Oldest incremental section removed to fit budget",
            ))
            idx -= 1

        return operations

    # Applying operations

    def _apply_operations(
        self,
        sections: List[PromptSection],
        operations: List[CurationOperation],
    ) -> str:
        """Apply curation operations to produce the curated prompt."""
        deleted_ids: set = set()
        merged_ids: set = set()
        replacements: Dict[str, str] = {}

        for op in operations:
            if op.op_type == "DELETE":
                for tid in op.target_ids:
                    if tid != "base":
                        deleted_ids.add(tid)

            elif op.op_type == "MERGE":
                if len(op.target_ids) < 2:
                    continue
                primary_id = op.target_ids[0]
                for tid in op.target_ids[1:]:
                    if tid != "base":
                        merged_ids.add(tid)
                if op.new_content:
                    replacements[primary_id] = op.new_content

            elif op.op_type == "UPDATE":
                for tid in op.target_ids:
                    if tid != "base" and op.new_content:
                        replacements[tid] = op.new_content

        # Reconstruct prompt preserving section order.
        parts: List[str] = []
        for section in sections:
            sid = section.section_id
            if sid in deleted_ids or sid in merged_ids:
                continue
            content = replacements.get(sid, section.content)
            if content.strip():
                parts.append(content)

        return "\n\n".join(parts)
