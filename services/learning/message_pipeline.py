"""消息处理流水线 — 协调后台学习、黑话挖掘、好感度更新"""
import asyncio
import time
from typing import Any, Optional, Set

from astrbot.api import logger

from ...core.interfaces import MessageData
from ...statics.messages import LogMessages
from ..monitoring.instrumentation import monitored
from .jargon_learning import JargonLearningModule
from .sample_filter import (
    extract_learning_event_metadata,
    filter_learning_messages,
    should_ignore_learning_sample,
)
from ...utils.persona_selection import get_event_persona_scope


class MessagePipeline:
    """消息处理流水线 — 每条消息的后台处理编排"""

    def __init__(
        self,
        plugin_config: Any,
        message_collector: Any,
        enhanced_interaction: Any,
        jargon_miner_manager: Optional[Any],
        jargon_statistical_filter: Optional[Any],
        v2_integration: Optional[Any],
        realtime_processor: Any,
        group_orchestrator: Any,
        conversation_goal_manager: Optional[Any],
        affection_manager: Any,
        db_manager: Any,
    ):
        self._config = plugin_config
        self._message_collector = message_collector
        self._enhanced_interaction = enhanced_interaction
        self._jargon_miner_manager = jargon_miner_manager
        self._jargon_statistical_filter = jargon_statistical_filter
        self._v2_integration = v2_integration
        self._realtime_processor = realtime_processor
        self._group_orchestrator = group_orchestrator
        self._conversation_goal_manager = conversation_goal_manager
        self._affection_manager = affection_manager
        self._db_manager = db_manager
        self._subtasks: Set[asyncio.Task] = set()
        self._jargon_learning = JargonLearningModule(
            config=plugin_config,
            message_collector=message_collector,
            jargon_miner_manager=jargon_miner_manager,
            jargon_statistical_filter=jargon_statistical_filter,
            db_manager=db_manager,
        )
        # Compatibility attributes for existing tests and integrations.
        self._active_jargon_groups = self._jargon_learning.active_groups
        self._last_jargon_trigger_counts = self._jargon_learning.last_trigger_counts
        self._group_raw_message_counts = (
            self._jargon_learning.group_raw_message_counts
        )
        self._groups_seeded = self._jargon_learning.groups_seeded

    # 后台学习流水线（6 步）

    @monitored
    async def process_learning(
        self,
        group_id: str,
        sender_id: str,
        message_text: str,
        event: Any,
    ) -> bool:
        """后台处理学习相关操作（非阻塞）

        通过 asyncio.create_task() 在后台运行。
        为避免 'Future attached to different loop' 错误，数据库操作包装在异常处理中。
        """
        message_collected = False
        try:
            event_metadata = extract_learning_event_metadata(event)
            persona_id = get_event_persona_scope(event, self._config)
            if should_ignore_learning_sample(
                message_text,
                sender_id=sender_id,
                **event_metadata,
            ):
                logger.debug(
                    "检测到指令或系统模板消息，跳过学习流水线: "
                    f"{message_text[:80]}"
                )
                return False

            # 1. 消息收集
            try:
                message_collected = bool(await self._message_collector.collect_message(
                    {
                        "sender_id": sender_id,
                        "sender_name": event.get_sender_name(),
                        "message": message_text,
                        "group_id": group_id,
                        "timestamp": time.time(),
                        "platform": event.get_platform_name(),
                        **event_metadata,
                    }
                ))
            except RuntimeError as e:
                if "attached to a different loop" in str(e):
                    logger.warning(
                        f"消息收集遇到事件循环问题（已知 MySQL 限制），"
                        f"消息将被跳过: {str(e)[:100]}"
                    )
                else:
                    raise
            except Exception as e:
                logger.error(f"消息收集失败: {e}")

            # Track raw message count in memory for jargon trigger
            if message_collected:
                self._jargon_learning.note_collected_message(group_id)

            # 2. 增强交互（多轮对话管理）
            try:
                await self._enhanced_interaction.update_conversation_context(
                    group_id, sender_id, message_text
                )
            except Exception as e:
                logger.error(LogMessages.ENHANCED_INTERACTION_FAILED.format(error=e))

            # 2.5 黑话统计预筛（<1ms, 零 LLM 成本）
            self._jargon_learning.update_statistical_filter(
                message_text, group_id, sender_id
            )

            # 3. 黑话挖掘 — 每收集 10 条消息触发一次
            if self._config.enable_jargon_learning:
                raw_message_count = await self._get_raw_message_count(group_id)
                if self._should_schedule_jargon_mining(
                    group_id, raw_message_count
                ):
                    self._spawn_jargon_task(group_id, raw_message_count)

            # 3.5 V2 per-message processing
            if self._v2_integration:
                try:
                    msg_data = MessageData(
                        message=message_text,
                        sender_id=sender_id,
                        sender_name=event.get_sender_name() or sender_id,
                        group_id=group_id,
                        timestamp=time.time(),
                        platform=event.get_platform_name() or "unknown",
                    )
                    await self._v2_integration.process_message(msg_data, group_id)
                except Exception as e:
                    logger.debug(f"V2 message processing failed: {e}")

            # 4. 实时学习
            if self._config.enable_realtime_learning:
                self._spawn(
                    self._realtime_processor.process_realtime_background(
                        group_id, message_text, sender_id, persona_id=persona_id
                    )
                )
            elif getattr(self._config, "enable_realtime_expression_learning", False):
                self._spawn(
                    self._realtime_processor.process_expression_learning_background(
                        group_id, message_text, sender_id, persona_id=persona_id
                    )
                )

            # 5. 智能启动学习任务
            if self._config.enable_style_learning:
                await self._group_orchestrator.smart_start_learning_for_group(group_id)

            # 6. 对话目标管理
            if self._config.enable_goal_driven_chat:
                try:
                    if self._conversation_goal_manager:
                        goal = await self._conversation_goal_manager.get_or_create_conversation_goal(
                            user_id=sender_id,
                            group_id=group_id,
                            user_message=message_text,
                        )
                        if goal:
                            goal_type = goal["final_goal"].get("type", "unknown")
                            goal_name = goal["final_goal"].get("name", "未知目标")
                            topic = goal["final_goal"].get("topic", "未知话题")
                            current_stage = goal["current_stage"].get("task", "初始化")
                            logger.debug(
                                f"[对话目标] 会话目标: {goal_name} "
                                f"(类型: {goal_type}), 话题: {topic}, "
                                f"当前阶段: {current_stage}"
                            )
                except Exception as e:
                    logger.error(f"对话目标处理失败: {e}", exc_info=True)

            return message_collected

        except Exception as e:
            logger.error(f"后台学习处理失败: {e}", exc_info=True)
            return False

    # 黑话挖掘

    @monitored
    async def mine_jargon(self, group_id: str) -> None:
        """后台黑话挖掘 — 完全异步、非阻塞

        1. 检查触发条件（频率控制）
        2. 获取统计候选词（零 LLM 成本）
        3. 无统计候选时回退到 LLM 提取
        4. 保存/更新到数据库并在阈值处触发推理
        """
        try:
            await self._jargon_learning.mine_jargon(group_id)

        except Exception as e:
            logger.error(
                f"[JargonMining] Background task failed (group={group_id}): {e}",
                exc_info=True,
            )

    # 好感度处理

    @monitored
    async def process_affection(
        self, group_id: str, sender_id: str, message_text: str
    ) -> None:
        """后台处理好感度更新（非阻塞）"""
        try:
            affection_result = (
                await self._affection_manager.process_message_interaction(
                    group_id, sender_id, message_text
                )
            )
            if affection_result.get("success"):
                logger.debug(
                    LogMessages.AFFECTION_PROCESSING_SUCCESS.format(
                        result=affection_result
                    )
                )
        except Exception as e:
            logger.error(LogMessages.AFFECTION_PROCESSING_FAILED.format(error=e))

    # Task tracking

    async def _get_raw_message_count(self, group_id: str) -> int:
        """Get raw message count for a group, seeded from DB once."""
        return await self._jargon_learning.get_raw_message_count(group_id)

    def _should_schedule_jargon_mining(
        self, group_id: str, raw_message_count: int
    ) -> bool:
        """Trigger jargon mining once per additional 10 messages per group."""
        return self._jargon_learning.should_schedule_mining(
            group_id,
            raw_message_count,
        )

    def _spawn_jargon_task(self, group_id: str, raw_message_count: int) -> None:
        """Spawn a jargon-mining task and track group-level trigger state."""
        self._jargon_learning.mark_mining_started(group_id, raw_message_count)
        task = self._spawn(self.mine_jargon(group_id))

        def _on_complete(_: asyncio.Task) -> None:
            self._jargon_learning.mark_mining_finished(group_id)

        task.add_done_callback(_on_complete)

    def _spawn(self, coro) -> asyncio.Task:
        """Create a background task and track it for shutdown cancellation."""
        task = asyncio.create_task(coro)
        self._subtasks.add(task)
        task.add_done_callback(self._subtasks.discard)
        return task

    async def cancel_subtasks(self) -> None:
        """Cancel all tracked subtasks (called during plugin shutdown)."""
        for task in list(self._subtasks):
            if not task.done():
                task.cancel()
        if self._subtasks:
            await asyncio.gather(*self._subtasks, return_exceptions=True)
        self._subtasks.clear()
