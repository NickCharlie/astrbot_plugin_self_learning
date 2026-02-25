"""
Persona reflection signal collector.

Inspired by the ACE (Agentic Context Engineering) Reflector pattern, this
service collects conversation quality signals from the database and
correlates them temporally with persona incremental sections.

Each incremental section is tagged as ``helpful``, ``harmful``, or
``neutral`` based on composite quality scores observed during the
time window after the section was appended.  These tags are consumed
by PersonaCurator to make data-driven curation decisions.

Design principles:
    - Zero additional LLM calls: all signals come from existing DB tables
      (ConversationQualityMetrics, AffectionInteraction).
    - Temporal correlation: quality is measured in the window between a
      section's timestamp and the next section's timestamp (or now).
    - Graceful degradation: returns None when the DB has insufficient data,
      allowing PersonaCurator to proceed without reflection context.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from astrbot.api import logger

from ...config import PluginConfig
from ..database import DatabaseManager
from .persona_curator import PromptSection


def _parse_prompt_sections(
    config: PluginConfig, prompt: str
) -> List[PromptSection]:
    """Parse persona prompt sections using PersonaCurator's parser."""
    from .persona_curator import PersonaCurator
    return PersonaCurator(config).parse_prompt_sections(prompt)


@dataclass
class SectionSignal:
    """Per-section effectiveness signal (analogous to ACE bullet tag)."""

    section_id: str
    tag: str  # "helpful" | "harmful" | "neutral"
    composite_score: float
    sample_count: int
    reason: str


@dataclass
class ReflectionContext:
    """Aggregated reflection context for PersonaCurator."""

    section_signals: List[SectionSignal] = field(default_factory=list)
    overall_quality_trend: str = "stable"  # "improving" | "stable" | "declining"
    avg_quality_score: float = 0.0
    lookback_hours: int = 48


class PersonaReflector:
    """Persona reflection signal collector.

    Collects quality metrics from the database, correlates them with persona
    incremental sections by timestamp, and produces per-section effectiveness
    tags for PersonaCurator.

    Usage::

        reflector = PersonaReflector(config, db_manager)
        ctx = await reflector.collect_reflection_context(group_id, prompt)
        if ctx:
            result = await curator.curate(group_id, prompt, reflection_context=ctx)
    """

    def __init__(
        self,
        config: PluginConfig,
        db_manager: DatabaseManager,
    ) -> None:
        self._config = config
        self._db_manager = db_manager
        self._lookback_hours = getattr(
            config, "persona_reflection_lookback_hours", 48
        )
        self._tag_threshold = getattr(
            config, "persona_reflection_tag_threshold", 0.05
        )

    async def collect_reflection_context(
        self,
        group_id: str,
        current_prompt: str,
    ) -> Optional[ReflectionContext]:
        """Collect quality signals and tag each incremental section.

        Returns ``None`` when insufficient data is available.
        """
        # Reuse PersonaCurator's parsing logic to split sections.
        sections = _parse_prompt_sections(self._config, current_prompt)

        incremental = [
            s for s in sections if s.section_type == "incremental"
        ]
        if not incremental:
            return None

        # Build time windows for each incremental section.
        windows = self._build_time_windows(incremental)
        if not windows:
            return None

        # Query quality metrics for all windows in a single DB pass.
        all_metrics = await self._query_quality_metrics(group_id, windows)
        if not all_metrics:
            logger.debug(
                f"[PersonaReflector] No quality metrics for group {group_id}"
            )
            return None

        # Compute per-section composite scores.
        section_scores = self._compute_section_scores(
            incremental, windows, all_metrics
        )

        # Tag sections relative to the overall average.
        signals = self._tag_sections(section_scores)

        # Determine overall quality trend.
        trend = self._determine_trend(section_scores)

        scored_values = [
            s["composite"] for s in section_scores if s["sample_count"] > 0
        ]
        avg_quality = (
            sum(scored_values) / len(scored_values) if scored_values else 0.0
        )

        logger.info(
            f"[PersonaReflector] Collected {len(signals)} section signals "
            f"for group {group_id} (trend={trend}, avg={avg_quality:.3f})"
        )

        return ReflectionContext(
            section_signals=signals,
            overall_quality_trend=trend,
            avg_quality_score=avg_quality,
            lookback_hours=self._lookback_hours,
        )

    # -- Internal helpers --

    def _build_time_windows(
        self, sections: List[PromptSection]
    ) -> List[dict]:
        """Build [start, end) time windows for each incremental section.

        Sections without a parseable timestamp are included with
        ``start=None, end=None`` and will be tagged as ``neutral``.
        """
        windows: List[dict] = []
        now_ts = datetime.now().timestamp()

        for i, section in enumerate(sections):
            start = self._parse_section_timestamp(section.timestamp)
            if start is None:
                windows.append({
                    "section_id": section.section_id,
                    "start": None,
                    "end": None,
                })
                continue

            # End of window is the start of the next section, or now.
            end = now_ts
            for j in range(i + 1, len(sections)):
                next_start = self._parse_section_timestamp(
                    sections[j].timestamp
                )
                if next_start is not None:
                    end = next_start
                    break

            windows.append({
                "section_id": section.section_id,
                "start": start,
                "end": end,
            })

        return windows

    @staticmethod
    def _parse_section_timestamp(ts_str: Optional[str]) -> Optional[float]:
        """Parse a section timestamp string into a Unix timestamp."""
        if not ts_str:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(ts_str.strip(), fmt).timestamp()
            except ValueError:
                continue
        return None

    async def _query_quality_metrics(
        self,
        group_id: str,
        windows: List[dict],
    ) -> List[dict]:
        """Query ConversationQualityMetrics for the group within the
        overall lookback window.

        Returns a list of dicts with score fields and ``calculated_at``.
        """
        # Determine global start from the earliest window.
        valid_starts = [
            w["start"] for w in windows if w["start"] is not None
        ]
        if not valid_starts:
            return []

        global_start = min(valid_starts)

        # Apply lookback cutoff so we don't query arbitrarily old data.
        lookback_cutoff = datetime.now().timestamp() - self._lookback_hours * 3600
        global_start = max(global_start, lookback_cutoff)

        try:
            from sqlalchemy import select
            from ...models.orm.message import ConversationQualityMetrics

            async with self._db_manager.get_session() as session:
                stmt = (
                    select(ConversationQualityMetrics)
                    .where(
                        ConversationQualityMetrics.group_id == group_id,
                        ConversationQualityMetrics.calculated_at >= global_start,
                    )
                    .order_by(ConversationQualityMetrics.calculated_at)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

            return [
                {
                    "calculated_at": row.calculated_at,
                    "coherence": row.coherence_score,
                    "relevance": row.relevance_score,
                    "engagement": row.engagement_score,
                    "sentiment": row.sentiment_alignment,
                }
                for row in rows
            ]
        except Exception as exc:
            logger.warning(
                f"[PersonaReflector] Quality metrics query failed: {exc}"
            )
            return []

    @staticmethod
    def _composite_score(metric: dict) -> float:
        """Compute a weighted composite quality score from a single row.

        Weights: coherence=0.3, relevance=0.3, engagement=0.2, sentiment=0.2
        """
        scores = []
        weights = []
        for key, w in [
            ("coherence", 0.3),
            ("relevance", 0.3),
            ("engagement", 0.2),
            ("sentiment", 0.2),
        ]:
            val = metric.get(key)
            if val is not None:
                scores.append(val * w)
                weights.append(w)

        if not weights:
            return 0.0
        return sum(scores) / sum(weights)

    def _compute_section_scores(
        self,
        sections: List[PromptSection],
        windows: List[dict],
        metrics: List[dict],
    ) -> List[dict]:
        """Compute composite quality scores per section window."""
        results = []
        for window in windows:
            sid = window["section_id"]
            start = window["start"]
            end = window["end"]

            if start is None or end is None:
                results.append({
                    "section_id": sid,
                    "composite": 0.0,
                    "sample_count": 0,
                })
                continue

            # Filter metrics falling within this window.
            in_window = [
                m for m in metrics
                if start <= m["calculated_at"] < end
            ]
            if not in_window:
                results.append({
                    "section_id": sid,
                    "composite": 0.0,
                    "sample_count": 0,
                })
                continue

            composite_scores = [
                self._composite_score(m) for m in in_window
            ]
            avg = sum(composite_scores) / len(composite_scores)
            results.append({
                "section_id": sid,
                "composite": avg,
                "sample_count": len(in_window),
            })

        return results

    def _tag_sections(
        self, section_scores: List[dict]
    ) -> List[SectionSignal]:
        """Tag each section as helpful, harmful, or neutral."""
        scored = [s for s in section_scores if s["sample_count"] > 0]
        if not scored:
            return [
                SectionSignal(
                    section_id=s["section_id"],
                    tag="neutral",
                    composite_score=0.0,
                    sample_count=0,
                    reason="No quality data available",
                )
                for s in section_scores
            ]

        overall_avg = sum(s["composite"] for s in scored) / len(scored)
        threshold = self._tag_threshold

        signals: List[SectionSignal] = []
        for s in section_scores:
            sid = s["section_id"]
            comp = s["composite"]
            count = s["sample_count"]

            if count == 0:
                signals.append(SectionSignal(
                    section_id=sid,
                    tag="neutral",
                    composite_score=0.0,
                    sample_count=0,
                    reason="No quality data in this window",
                ))
            elif comp > overall_avg + threshold:
                signals.append(SectionSignal(
                    section_id=sid,
                    tag="helpful",
                    composite_score=comp,
                    sample_count=count,
                    reason=(
                        f"Quality above average "
                        f"({comp:.3f} > {overall_avg:.3f}+{threshold})"
                    ),
                ))
            elif comp < overall_avg - threshold:
                signals.append(SectionSignal(
                    section_id=sid,
                    tag="harmful",
                    composite_score=comp,
                    sample_count=count,
                    reason=(
                        f"Quality below average "
                        f"({comp:.3f} < {overall_avg:.3f}-{threshold})"
                    ),
                ))
            else:
                signals.append(SectionSignal(
                    section_id=sid,
                    tag="neutral",
                    composite_score=comp,
                    sample_count=count,
                    reason="Quality near average",
                ))

        return signals

    @staticmethod
    def _determine_trend(section_scores: List[dict]) -> str:
        """Determine overall quality trend by comparing halves."""
        scored = [s for s in section_scores if s["sample_count"] > 0]
        if len(scored) < 2:
            return "stable"

        mid = len(scored) // 2
        first_half = scored[:mid]
        second_half = scored[mid:]

        avg_first = sum(s["composite"] for s in first_half) / len(first_half)
        avg_second = sum(s["composite"] for s in second_half) / len(second_half)

        delta = avg_second - avg_first
        if delta > 0.03:
            return "improving"
        elif delta < -0.03:
            return "declining"
        return "stable"