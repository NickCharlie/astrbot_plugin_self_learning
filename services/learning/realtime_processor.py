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

    async def process_message_realtime(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Process a single message in realtime — filter + expression learning."""
        try:
            # Basic guards
            if len(message_text.strip()) < self._config.message_min_length:
                return
            if len(message_text) > self._config.message_max_length:
                return
            if message_text.strip() in ("", "???", "。。。", "...", "嗯", "哦", "额"):
                return

            # Expression-style learning (bypasses filtering)
            await self._process_expression_style_learning(
                group_id, message_text, sender_id
            )

            # Batch mode: skip LLM filtering if disabled
            if not self._config.enable_realtime_llm_filter:
                await self._message_collector.add_filtered_message(
                    {
                        "message": message_text,
                        "sender_id": sender_id,
                        "group_id": group_id,
                        "timestamp": time.time(),
                        "confidence": 0.6,
                    }
                )
                self._learning_stats.filtered_messages += 1
                if not hasattr(self._config, "filtered_messages"):
                    self._config.filtered_messages = 0
                self._config.filtered_messages = (
                    self._learning_stats.filtered_messages
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
                if not hasattr(self._config, "filtered_messages"):
                    self._config.filtered_messages = 0
                self._config.filtered_messages = (
                    self._learning_stats.filtered_messages
                )

        except Exception as e:
            logger.error(
                StatusMessages.REALTIME_PROCESSING_ERROR.format(error=e),
                exc_info=True,
            )

    # Expression-style learning

    async def _process_expression_style_learning(
        self, group_id: str, message_text: str, sender_id: str
    ) -> None:
        """Learn expression styles directly from raw messages."""
        try:
            stats = await self._message_collector.get_statistics(group_id)
            raw_message_count = stats.get("raw_messages", 0)

            if raw_message_count < 5:
                logger.debug(
                    f"群组 {group_id} 原始消息数量不足，当前：{raw_message_count}，需要至少5条"
                )
                return

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

            expression_learner = (
                self._factory_manager.get_component_factory()
                .create_expression_pattern_learner()
            )
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
                    await self._apply_style_to_prompt_temporarily(
                        group_id, learned_patterns
                    )
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
                            f"群组 {group_id} 表达风格学习结果已临时应用到prompt，"
                            "并已提交人格审查"
                        )
                    else:
                        logger.info(
                            f"群组 {group_id} 表达风格学习结果已临时应用到prompt"
                        )
            except Exception as e:
                logger.error(f"处理表达风格学习结果失败: {e}")

            self._learning_stats.style_updates += 1

            if self.update_system_prompt_callback:
                await self.update_system_prompt_callback(group_id)
                logger.info(
                    f"群组 {group_id} 表达风格学习结果已应用到system_prompt"
                )

        except Exception as e:
            logger.error(f"群组 {group_id} 表达风格学习处理失败: {e}")

    # Temporary style application

    async def _apply_style_to_prompt_temporarily(
        self, group_id: str, learned_patterns: List[Any]
    ) -> None:
        """Apply learned style patterns to the prompt temporarily."""
        try:
            if not learned_patterns:
                return

            style_descriptions: List[str] = []
            for pattern in learned_patterns[:3]:
                situation = (
                    pattern.situation
                    if hasattr(pattern, "situation")
                    else pattern.get("situation", "")
                )
                expression = (
                    pattern.expression
                    if hasattr(pattern, "expression")
                    else pattern.get("expression", "")
                )
                if situation and expression:
                    style_descriptions.append(
                        f'当{situation}时，可以使用"{expression}"这样的表达'
                    )

            if not style_descriptions:
                return

            bullet_list = "\n".join(f"• {desc}" for desc in style_descriptions)
            style_prompt = (
                "【临时表达风格特征】（基于最近学习）\n"
                "在回复时可以参考以下表达方式：\n"
                f"{bullet_list}\n\n"
                "注意：这些是临时学习的风格特征，应自然融入回复，不要刻意模仿。"
            )

            success = await self._temporary_persona_updater.apply_temporary_style_update(
                group_id, style_prompt
            )

            if success:
                logger.info(
                    f"群组 {group_id} 表达风格已临时应用到prompt，"
                    f"包含 {len(style_descriptions)} 个风格特征"
                )
            else:
                logger.warning(f"群组 {group_id} 表达风格临时应用失败")

        except Exception as e:
            logger.error(f"临时应用风格到prompt失败: {e}")

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
            if msg.get("sender_id") == sender_id:
                continue

            content = msg.get("message", "")
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
