"""消息处理流水线 — 协调后台学习、黑话挖掘、好感度更新"""
import asyncio
import time
from typing import Any, Optional

from astrbot.api import logger

from ...core.interfaces import MessageData
from ...statics.messages import LogMessages


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

    # ------------------------------------------------------------------
    # 后台学习流水线（6 步）
    # ------------------------------------------------------------------

    async def process_learning(
        self,
        group_id: str,
        sender_id: str,
        message_text: str,
        event: Any,
    ) -> None:
        """后台处理学习相关操作（非阻塞）

        通过 asyncio.create_task() 在后台运行。
        为避免 'Future attached to different loop' 错误，数据库操作包装在异常处理中。
        """
        try:
            # 1. 消息收集
            try:
                await self._message_collector.collect_message(
                    {
                        "sender_id": sender_id,
                        "sender_name": event.get_sender_name(),
                        "message": message_text,
                        "group_id": group_id,
                        "timestamp": time.time(),
                        "platform": event.get_platform_name(),
                    }
                )
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

            # 2. 增强交互（多轮对话管理）
            try:
                await self._enhanced_interaction.update_conversation_context(
                    group_id, sender_id, message_text
                )
            except Exception as e:
                logger.error(LogMessages.ENHANCED_INTERACTION_FAILED.format(error=e))

            # 2.5 黑话统计预筛（<1ms, 零 LLM 成本）
            if self._jargon_statistical_filter:
                try:
                    self._jargon_statistical_filter.update_from_message(
                        message_text, group_id, sender_id
                    )
                except Exception:
                    pass  # best-effort

            # 3. 黑话挖掘 — 每收集 10 条消息触发一次
            stats = await self._message_collector.get_statistics(group_id)
            raw_message_count = stats.get("raw_messages", 0)
            if raw_message_count % 10 == 0 and raw_message_count >= 10:
                asyncio.create_task(self.mine_jargon(group_id))

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
                asyncio.create_task(
                    self._realtime_processor.process_realtime_background(
                        group_id, message_text, sender_id
                    )
                )

            # 5. 智能启动学习任务
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
                            logger.info(
                                f"✅ [对话目标] 会话目标: {goal_name} "
                                f"(类型: {goal_type}), 话题: {topic}, "
                                f"当前阶段: {current_stage}"
                            )
                except Exception as e:
                    logger.error(f"对话目标处理失败: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"后台学习处理失败: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # 黑话挖掘
    # ------------------------------------------------------------------

    async def mine_jargon(self, group_id: str) -> None:
        """后台黑话挖掘 — 完全异步、非阻塞

        1. 检查触发条件（频率控制）
        2. 获取统计候选词（零 LLM 成本）
        3. 无统计候选时回退到 LLM 提取
        4. 保存/更新到数据库并在阈值处触发推理
        """
        try:
            if not self._jargon_miner_manager:
                logger.debug("[JargonMining] JargonMinerManager not initialised, skip")
                return

            jargon_miner = self._jargon_miner_manager.get_or_create_miner(group_id)

            stats = await self._message_collector.get_statistics(group_id)
            recent_message_count = stats.get("raw_messages", 0)

            if not jargon_miner.should_trigger(recent_message_count):
                logger.debug(
                    f"[JargonMining] Group {group_id} trigger conditions not met"
                )
                return

            recent_messages = await self._db_manager.get_recent_raw_messages(
                group_id, limit=30
            )

            if len(recent_messages) < 10:
                logger.debug(
                    f"[JargonMining] Group {group_id} insufficient messages "
                    f"({len(recent_messages)}<10)"
                )
                return

            logger.info(
                f"[JargonMining] Analysing {len(recent_messages)} messages "
                f"from group {group_id}"
            )

            chat_messages = "\n".join(
                [
                    f"{msg.get('sender_id', 'unknown')}: {msg.get('message', '')}"
                    for msg in recent_messages
                ]
            )

            statistical_candidates = None
            if self._jargon_statistical_filter:
                statistical_candidates = (
                    self._jargon_statistical_filter.get_jargon_candidates(
                        group_id, top_k=20
                    )
                )
                if not statistical_candidates:
                    statistical_candidates = None

            await jargon_miner.run_once(
                chat_messages,
                len(recent_messages),
                statistical_candidates=statistical_candidates,
            )

            logger.debug(f"[JargonMining] Group {group_id} learning complete")

        except Exception as e:
            logger.error(
                f"[JargonMining] Background task failed (group={group_id}): {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 好感度处理
    # ------------------------------------------------------------------

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
