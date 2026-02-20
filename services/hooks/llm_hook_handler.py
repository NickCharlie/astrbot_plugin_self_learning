"""LLM Hook handler — parallel context retrieval, prompt injection, performance tracking.

Orchestrates all context providers (social, V2, diversity, jargon, session updates)
in parallel, merges results, and injects them into the LLM request.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .perf_tracker import PerfTracker


class LLMHookHandler:
    """Orchestrate LLM Hook context injection.

    Runs all context providers in parallel via ``asyncio.gather``, merges
    results in priority order, and records timing data.

    Args:
        plugin_config: Plugin configuration object.
        diversity_manager: Diversity prompt builder service.
        social_context_injector: Social context injector service.
        v2_integration: V2 learning integration service.
        jargon_query_service: Jargon query service.
        temporary_persona_updater: Session-level persona updater.
        perf_tracker: ``PerfTracker`` for recording timing samples.
        group_id_to_unified_origin: Shared mapping from group_id to UMO.
    """

    def __init__(
        self,
        plugin_config: Any,
        diversity_manager: Any,
        social_context_injector: Any,
        v2_integration: Any,
        jargon_query_service: Any,
        temporary_persona_updater: Any,
        perf_tracker: PerfTracker,
        group_id_to_unified_origin: Dict[str, str],
    ) -> None:
        self._config = plugin_config
        self._diversity_manager = diversity_manager
        self._social_context_injector = social_context_injector
        self._v2_integration = v2_integration
        self._jargon_query_service = jargon_query_service
        self._temporary_persona_updater = temporary_persona_updater
        self._perf_tracker = perf_tracker
        self._group_id_to_unified_origin = group_id_to_unified_origin

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle(self, event: AstrMessageEvent, req: Any) -> None:
        """Process an LLM request hook — inject context into *req*."""
        hook_start = time.time()
        social_ms = v2_ms = diversity_ms = jargon_ms = 0.0

        try:
            if req is None:
                logger.warning("[LLM Hook] req 参数为 None，跳过注入")
                return

            if not self._diversity_manager:
                logger.debug("[LLM Hook] diversity_manager未初始化,跳过多样性注入")
                return

            group_id = event.get_group_id() or event.get_sender_id()
            user_id = event.get_sender_id()

            # Maintain group_id → unified_msg_origin mapping
            if hasattr(event, "unified_msg_origin") and event.unified_msg_origin:
                self._group_id_to_unified_origin[group_id] = event.unified_msg_origin
                logger.debug(f"[LLM Hook] 更新映射: {group_id} -> {event.unified_msg_origin}")

            if not req.prompt:
                logger.debug("[LLM Hook] req.prompt为空,跳过多样性注入")
                return

            original_prompt_length = len(req.prompt)
            logger.info(
                f"✅ [LLM Hook] 开始注入多样性增强 "
                f"(group: {group_id}, 原prompt长度: {original_prompt_length})"
            )

            prompt_injections: List[str] = []
            logger.debug("[LLM Hook] 跳过基础人格注入（框架已处理），专注于增量内容")

            # ----------------------------------------------------------
            # Parallel context retrieval
            # ----------------------------------------------------------
            social_result: Optional[str] = None
            v2_result: Optional[Dict[str, Any]] = None
            diversity_result: Optional[str] = None
            jargon_result: Optional[str] = None

            async def _timed_social() -> None:
                nonlocal social_result, social_ms
                t0 = time.time()
                social_result = await self._fetch_social(group_id, user_id)
                social_ms = (time.time() - t0) * 1000

            async def _timed_v2() -> None:
                nonlocal v2_result, v2_ms
                t0 = time.time()
                v2_result = await self._fetch_v2(req.prompt, group_id)
                v2_ms = (time.time() - t0) * 1000

            async def _timed_diversity() -> None:
                nonlocal diversity_result, diversity_ms
                t0 = time.time()
                diversity_result = await self._fetch_diversity(group_id)
                diversity_ms = (time.time() - t0) * 1000

            async def _timed_jargon() -> None:
                nonlocal jargon_result, jargon_ms
                t0 = time.time()
                jargon_result = await self._fetch_jargon(event, group_id)
                jargon_ms = (time.time() - t0) * 1000

            await asyncio.gather(
                _timed_social(),
                _timed_v2(),
                _timed_diversity(),
                _timed_jargon(),
            )

            # ----------------------------------------------------------
            # Merge results in priority order
            # ----------------------------------------------------------
            self._collect_social(social_result, group_id, prompt_injections)
            self._collect_v2(v2_result, v2_ms, prompt_injections)
            self._collect_diversity(diversity_result, prompt_injections)
            self._collect_jargon(jargon_result, prompt_injections)
            self._collect_session_updates(group_id, prompt_injections)

            # ----------------------------------------------------------
            # Inject into request
            # ----------------------------------------------------------
            if prompt_injections:
                self._inject(req, prompt_injections, hook_start)
            else:
                logger.debug("[LLM Hook] 没有可注入的增量内容")

            # Record perf data
            total_ms = (time.time() - hook_start) * 1000
            self._perf_tracker.record(
                {
                    "ts": time.time(),
                    "total_ms": round(total_ms, 1),
                    "social_ctx_ms": round(social_ms, 1),
                    "v2_ctx_ms": round(v2_ms, 1),
                    "diversity_ms": round(diversity_ms, 1),
                    "jargon_ms": round(jargon_ms, 1),
                    "group_id": group_id,
                }
            )

        except Exception as e:
            logger.error(f"❌ [LLM Hook] 框架层面注入多样性失败: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Context fetchers
    # ------------------------------------------------------------------

    async def _fetch_social(
        self, group_id: str, user_id: str
    ) -> Optional[str]:
        if not self._social_context_injector:
            logger.debug("[LLM Hook] social_context_injector未初始化，跳过社交上下文注入")
            return None
        try:
            return await self._social_context_injector.format_complete_context(
                group_id=group_id,
                user_id=user_id,
                include_social_relations=self._config.include_social_relations,
                include_affection=self._config.include_affection_info,
                include_mood=False,
                include_expression_patterns=True,
                include_psychological=True,
                include_behavior_guidance=True,
                include_conversation_goal=self._config.enable_goal_driven_chat,
                enable_protection=True,
            )
        except Exception as e:
            logger.warning(f"[LLM Hook] 注入社交上下文失败: {e}")
            return None

    async def _fetch_v2(
        self, prompt: str, group_id: str
    ) -> Optional[Dict[str, Any]]:
        if not self._v2_integration:
            return None
        try:
            return await self._v2_integration.get_enhanced_context(prompt, group_id)
        except Exception as e:
            logger.debug(f"[LLM Hook] V2 context retrieval failed: {e}")
            return None

    async def _fetch_diversity(self, group_id: str) -> Optional[str]:
        try:
            content = await self._diversity_manager.build_diversity_prompt_injection(
                "",
                group_id=group_id,
                inject_style=True,
                inject_pattern=True,
                inject_variation=True,
                inject_history=True,
            )
            return content.strip() if content else None
        except Exception as e:
            logger.warning(f"[LLM Hook] 多样性增强失败: {e}")
            return None

    async def _fetch_jargon(
        self, event: AstrMessageEvent, group_id: str
    ) -> Optional[str]:
        if not self._jargon_query_service:
            logger.debug("[LLM Hook] jargon_query_service未初始化，跳过黑话注入")
            return None
        try:
            user_message = (
                event.message_str
                if hasattr(event, "message_str")
                else str(event.get_message())
            )
            return await self._jargon_query_service.check_and_explain_jargon(
                text=user_message, chat_id=group_id
            )
        except Exception as e:
            logger.warning(f"[LLM Hook] 注入黑话理解失败: {e}")
            return None

    # ------------------------------------------------------------------
    # Result collectors
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_social(
        result: Optional[str], group_id: str, out: List[str]
    ) -> None:
        if result:
            out.append(result)
            logger.info(f"✅ [LLM Hook] 已准备完整社交上下文 (长度: {len(result)})")
        else:
            logger.debug(f"[LLM Hook] 群组 {group_id} 暂无社交上下文")

    @staticmethod
    def _collect_v2(
        result: Optional[Dict[str, Any]], ms: float, out: List[str]
    ) -> None:
        if not result:
            return
        v2_parts: List[str] = []
        if result.get("knowledge_context"):
            v2_parts.append(f"[Related Knowledge]\n{result['knowledge_context']}")
        if result.get("related_memories"):
            memories_text = "\n".join(result["related_memories"][:5])
            v2_parts.append(f"[Related Memories]\n{memories_text}")
        if result.get("few_shot_examples"):
            examples_text = "\n".join(result["few_shot_examples"][:3])
            v2_parts.append(f"[Style Examples]\n{examples_text}")
        if v2_parts:
            out.append("\n\n".join(v2_parts))
            logger.info(f"[LLM Hook] V2 context injected ({len(v2_parts)} sections, {ms:.0f}ms)")
        else:
            logger.debug(f"[LLM Hook] V2 context empty ({ms:.0f}ms)")

    @staticmethod
    def _collect_diversity(result: Optional[str], out: List[str]) -> None:
        if result:
            out.append(result)
            logger.info(f"✅ [LLM Hook] 已准备多样性增强内容 (长度: {len(result)})")

    @staticmethod
    def _collect_jargon(result: Optional[str], out: List[str]) -> None:
        if result:
            out.append(result)
            logger.info(f"✅ [LLM Hook] 已准备黑话理解内容 (长度: {len(result)})")
        else:
            logger.debug("[LLM Hook] 用户消息中未检测到已知黑话")

    def _collect_session_updates(
        self, group_id: str, out: List[str]
    ) -> None:
        if not self._temporary_persona_updater:
            logger.debug("[LLM Hook] temporary_persona_updater未初始化，跳过会话级更新注入")
            return
        try:
            session_updates = self._temporary_persona_updater.session_updates.get(
                group_id, []
            )
            if session_updates:
                updates_text = "\n\n".join(session_updates)
                out.append(updates_text)
                logger.info(
                    f"✅ [LLM Hook] 已准备会话级更新 "
                    f"(会话: {group_id}, 更新数: {len(session_updates)}, "
                    f"长度: {len(updates_text)})"
                )
            else:
                logger.debug(f"[LLM Hook] 会话 {group_id} 暂无增量更新")
        except Exception as e:
            logger.warning(f"[LLM Hook] 注入会话级更新失败: {e}")

    # ------------------------------------------------------------------
    # Injection
    # ------------------------------------------------------------------

    def _inject(
        self, req: Any, injections: List[str], hook_start: float
    ) -> None:
        injection_text = "\n\n".join(injections)
        target = getattr(self._config, "llm_hook_injection_target", "system_prompt")

        if target == "system_prompt":
            if not req.system_prompt:
                req.system_prompt = ""
            original = len(req.system_prompt)
            req.system_prompt += "\n\n" + injection_text
            added = len(req.system_prompt) - original
            logger.info(
                f"✅ [LLM Hook] System Prompt 注入完成 - "
                f"原长度: {original}, 新增: {added}, 总长度: {len(req.system_prompt)}"
            )
            logger.info("💡 [LLM Hook] 注入位置: system_prompt (不会被保存到对话历史)")
        else:
            original = len(req.prompt)
            req.prompt += "\n\n" + injection_text
            added = len(req.prompt) - original
            logger.info(
                f"✅ [LLM Hook] Prompt 注入完成 - "
                f"原长度: {original}, 新增: {added}, 总长度: {len(req.prompt)}"
            )
            logger.warning(
                "⚠️ [LLM Hook] 注入位置: prompt (会被保存到对话历史，可能导致token超限)"
            )

        current_style = self._diversity_manager.get_current_style()
        current_pattern = self._diversity_manager.get_current_pattern()
        logger.info(
            f"✅ [LLM Hook] 当前语言风格: {current_style}, 回复模式: {current_pattern}"
        )
        logger.info(
            f"✅ [LLM Hook] 注入内容数量: {len(injections)}项, "
            f"耗时: {time.time() - hook_start:.3f}s"
        )
        logger.debug(f"✅ [LLM Hook] 注入内容预览: {injection_text[:200]}...")
