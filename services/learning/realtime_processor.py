"""Realtime message processing — expression-style learning and message filtering.

Handles the per-message processing pipeline that runs in the background
after each incoming message.
"""

import re
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from astrbot.api import logger

from ...core.interfaces import MessageData
from ...statics.messages import StatusMessages
from .dialog_analyzer import DialogAnalyzer
from .sample_filter import should_ignore_learning_sample


class RealtimeProcessor:
    """Process incoming messages for realtime learning and filtering.

    Orchestrates expression-style learning, message LLM filtering, and
    temporary persona updates.

    Args:
        plugin_config: Plugin configuration object.
        message_collector: Message collector service.
        multidimensional_analyzer: Analyzer for LLM-based message filtering.
        persona_manager: Persona manager for current persona retrieval.
        temporary_persona_updater: Service for temporary style prompt updates.
        dialog_analyzer: ``DialogAnalyzer`` for few-shot generation.
        learning_stats: Shared ``LearningStats`` dataclass instance.
        factory_manager: ``FactoryManager`` for component creation.
        db_manager: Database manager for raw message retrieval.
    """

    def __init__(
        self,
        plugin_config: Any,
        message_collector: Any,
        multidimensional_analyzer: Any,
        persona_manager: Any,
        temporary_persona_updater: Any,
        dialog_analyzer: DialogAnalyzer,
        learning_stats: Any,
        factory_manager: Any,
        db_manager: Any,
    ) -> None:
        self._config = plugin_config
        self._message_collector = message_collector
        self._multidimensional_analyzer = multidimensional_analyzer
        self._persona_manager = persona_manager
        self._temporary_persona_updater = temporary_persona_updater
        self._dialog_analyzer = dialog_analyzer
        self._learning_stats = learning_stats
        self._factory_manager = factory_manager
        self._db_manager = db_manager
        self._expression_learner = None  # lazily resolved, cached
        self._last_expression_trigger_counts: Dict[str, int] = {}
        self._last_expression_learning_times: Dict[str, float] = {}

        # Callback set by the plugin to trigger incremental prompt updates
        self.update_system_prompt_callback: Optional[
            Callable[[str], Coroutine[Any, Any, None]]
        ] = None

    # Public API

    async def process_realtime_background(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Background wrapper — fully async, never blocks the main flow."""
        try:
            await self.process_message_realtime(group_id, message_text, sender_id)
        except Exception as e:
            logger.error(
                f"实时学习后台处理失败 (group={group_id}): {e}", exc_info=True
            )

    async def process_expression_learning_background(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Run expression-style learning without enabling realtime filtering."""
        try:
            await self.process_expression_learning(group_id, message_text, sender_id)
        except Exception as e:
            logger.error(
                f"表达风格学习后台处理失败 (group={group_id}): {e}",
                exc_info=True,
            )

    async def process_expression_learning(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Process a single message for expression-style learning only."""
        if self._should_skip_message(message_text):
            return
        if not self._config.enable_expression_patterns:
            return
        await self._process_expression_style_learning(
            group_id, message_text, sender_id
        )

    async def process_message_realtime(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Process a single message in realtime — filter + expression learning."""
        try:
            # Basic guards
            if self._should_skip_message(message_text):
                return

            # Expression-style learning (bypasses filtering)
            if self._config.enable_expression_patterns:
                await self._process_expression_style_learning(
                    group_id, message_text, sender_id
                )

            # Batch mode: skip realtime LLM filtering completely when disabled.
            if not getattr(self._config, "enable_realtime_llm_filter", False):
                logger.debug(
                    f"群组 {group_id} 实时LLM筛选未启用，跳过实时 filtered_messages 写入"
                )
                return
            current_persona_description = (
                await self._persona_manager.get_current_persona_description(group_id)
            )

            if await self._multidimensional_analyzer.filter_message_with_llm(
                message_text, current_persona_description
            ):
                await self._message_collector.add_filtered_message(
                    {
                        "message": message_text,
                        "sender_id": sender_id,
                        "group_id": group_id,
                        "timestamp": time.time(),
                        "confidence": 0.8,
                    }
                )
                self._learning_stats.filtered_messages += 1

        except Exception as e:
            logger.error(
                StatusMessages.REALTIME_PROCESSING_ERROR.format(error=e),
                exc_info=True,
            )

    def _should_skip_message(self, message_text: str) -> bool:
        """Apply the shared message guards for realtime sub-pipelines."""
        stripped = message_text.strip()
        if should_ignore_learning_sample(stripped):
            return True
        if len(stripped) < self._config.message_min_length:
            return True
        if len(message_text) > self._config.message_max_length:
            return True
        if stripped in ("", "???", "。。。", "...", "嗯", "哦", "额"):
            return True
        return False

    # Expression-style learning

    async def _process_expression_style_learning(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Learn expression styles directly from raw messages."""
        try:
            now = time.time()
            min_interval = max(
                0,
                int(
                    getattr(
                        self._config,
                        "expression_learning_min_interval_seconds",
                        3600,
                    )
                    or 0
                ),
            )
            last_learning_time = self._last_expression_learning_times.get(group_id, 0)
            if min_interval and last_learning_time and now - last_learning_time < min_interval:
                remaining = int(min_interval - (now - last_learning_time))
                logger.debug(
                    f"群组 {group_id} 表达风格学习处于冷却中，"
                    f"剩余约 {remaining} 秒"
                )
                return

            stats = await self._message_collector.get_statistics(group_id)
            raw_message_count = stats.get("raw_messages", 0)

            if raw_message_count < 5:
                logger.debug(
                    f"群组 {group_id} 原始消息数量不足，当前：{raw_message_count}，需要至少5条"
                )
                return

            trigger_messages = max(
                1,
                int(getattr(self._config, "expression_learning_trigger_messages", 10) or 10),
            )
            last_trigger = self._last_expression_trigger_counts.get(group_id, 0)
            if raw_message_count - last_trigger < trigger_messages:
                logger.debug(
                    f"群组 {group_id} 表达风格学习未达触发增量，"
                    f"当前：{raw_message_count}，上次：{last_trigger}，阈值：{trigger_messages}"
                )
                return
            self._last_expression_trigger_counts[group_id] = raw_message_count
            self._last_expression_learning_times[group_id] = now

            logger.info(
                f"群组 {group_id} 开始表达风格学习，当前消息数：{raw_message_count}"
            )

            recent_raw_messages = await self._db_manager.get_recent_raw_messages(
                group_id, limit=25
            )
            if not recent_raw_messages or len(recent_raw_messages) < 3:
                logger.debug(
                    f"群组 {group_id} 原始消息数量不足，数据库中只有 "
                    f"{len(recent_raw_messages) if recent_raw_messages else 0} 条"
                )
                return

            message_data_list = self._build_message_data_list(
                recent_raw_messages, group_id, sender_id
            )
            if message_data_list:
                message_data_list = await self._merge_bot_messages_for_pairs(
                    group_id,
                    message_data_list,
                )

            if len(message_data_list) < 3:
                logger.debug(
                    f"群组 {group_id} 有效学习消息不足3条，跳过表达风格学习，"
                    f"当前：{len(message_data_list)}"
                )
                return

            logger.info(
                f"群组 {group_id} 准备进行表达风格学习，"
                f"有效消息数：{len(message_data_list)}"
            )

            if not self._expression_learner:
                try:
                    self._expression_learner = (
                        self._factory_manager.get_component_factory()
                        .create_expression_pattern_learner()
                    )
                except Exception:
                    logger.debug("表达模式学习器尚未就绪，跳过本次风格学习")
                    return
            expression_learner = self._expression_learner
            if not expression_learner:
                logger.warning("表达模式学习器未正确初始化")
                return

            learning_success = await expression_learner.trigger_learning_for_group(
                group_id, message_data_list
            )
            if not learning_success:
                logger.debug(f"群组 {group_id} 表达风格学习未产生有效结果")
                return

            logger.info(f"群组 {group_id} 表达风格学习成功")

            try:
                learned_patterns = await expression_learner.get_expression_patterns(
                    group_id, limit=5
                )
                if learned_patterns:
                    few_shots_content = (
                        await self._dialog_analyzer.generate_few_shots_dialog(
                            group_id, message_data_list
                        )
                    )
                    if few_shots_content:
                        await self._dialog_analyzer.create_style_learning_review_request(
                            group_id, learned_patterns, few_shots_content
                        )
                        logger.info(
                            f"群组 {group_id} 表达风格学习结果已提交人格审查，"
                            "等待批准后再写入 begin_dialogs"
                        )
                    else:
                        logger.info(
                            f"群组 {group_id} 表达风格学习成功，"
                            "但未生成可审查的 few-shot 示例，跳过人格写入"
                        )
            except Exception as e:
                logger.error(f"处理表达风格学习结果失败: {e}")

            self._learning_stats.style_updates += 1

        except Exception as e:
            logger.error(f"群组 {group_id} 表达风格学习处理失败: {e}")

    # Helpers

    @staticmethod
    def _build_message_data_list(
        recent_raw_messages: List[Dict[str, Any]],
        group_id: str,
        sender_id: str,
    ) -> List[MessageData]:
        """Convert raw DB messages to filtered ``MessageData`` objects."""
        at_pattern = re.compile(r"@[^\s]+\s+")
        result: List[MessageData] = []

        for msg in recent_raw_messages:
            content = msg.get("message", "")
            sender = msg.get("sender_id", "")
            if should_ignore_learning_sample(content, sender_id=sender):
                continue
            if len(content.strip()) < 5 or len(content) > 500:
                continue
            if content.strip() in ("", "???", "。。。", "...", "嗯", "哦", "额"):
                continue

            processed = content
            if "@" in content:
                processed = at_pattern.sub("", content).strip()
                if len(processed.strip()) < 5:
                    continue

            result.append(
                MessageData(
                    sender_id=msg.get("sender_id", ""),
                    sender_name=msg.get("sender_name", ""),
                    message=processed,
                    group_id=group_id,
                    timestamp=msg.get("timestamp", time.time()),
                    platform=msg.get("platform", "default"),
                    message_id=msg.get("id"),
                    reply_to=None,
                )
            )

        return result

    async def _merge_bot_messages_for_pairs(
        self,
        group_id: str,
        user_messages: List[MessageData],
    ) -> List[MessageData]:
        """Merge stored bot replies into the raw-message timeline."""
        if not user_messages or not self._db_manager:
            return user_messages

        try:
            async with self._db_manager.get_session() as session:
                from sqlalchemy import select, desc
                from ...models.orm.message import BotMessage

                stmt = (
                    select(BotMessage)
                    .where(BotMessage.group_id == group_id)
                    .order_by(desc(BotMessage.timestamp))
                    .limit(len(user_messages))
                )
                result = await session.execute(stmt)
                bot_messages = []
                for row in result.scalars().all():
                    if should_ignore_learning_sample(
                        row.message,
                        sender_id="bot",
                        is_bot=True,
                    ):
                        continue
                    bot_messages.append(
                        MessageData(
                            sender_id="bot",
                            sender_name="bot",
                            message=row.message,
                            group_id=group_id,
                            timestamp=float(row.timestamp),
                            platform="bot",
                            message_id=str(row.id),
                        )
                    )
        except Exception as exc:
            logger.debug(f"合并 Bot 回复失败，使用用户消息继续: {exc}")
            return user_messages

        merged = user_messages + bot_messages
        merged.sort(key=lambda msg: msg.timestamp)
        return merged
