"""Few-shot dialog generation, dialog-pair validation, and style review management.

Extracted from main.py to encapsulate dialog analysis logic used during
expression-style learning.
"""

import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ...constants import UPDATE_TYPE_STYLE_LEARNING
from ..monitoring.instrumentation import monitored
from .conversation_samples import (
    extract_human_dialog_pairs,
    human_dialog_timeline,
    message_timestamp,
    message_value,
)


class DialogAnalyzer:
    """Generates few-shot dialog examples and manages style-learning reviews.

    Dependencies are injected via constructor to keep this class testable
    and decoupled from the plugin instance.

    Args:
        factory_manager: ``FactoryManager`` for obtaining service/component factories.
        db_manager: Database manager with ``create_style_learning_review``
            and ``get_db_connection`` support.
    """

    def __init__(self, factory_manager: Any, db_manager: Any) -> None:
        self._factory_manager = factory_manager
        self._db_manager = db_manager

    # Few-shot dialog generation

    @monitored
    async def generate_few_shots_dialog(
        self, group_id: str, message_data_list: List[Any]
    ) -> str:
        """Generate few-shot dialog content from collected messages.

        Requires at least 10 messages and 3 valid dialog pairs to produce
        output. Returns an empty string when the threshold is not met.
        """
        try:
            if len(message_data_list) < 10:
                logger.debug(
                    f"群组 {group_id} 消息数量不足10条"
                    f"（当前{len(message_data_list)}条），跳过Few Shots生成"
                )
                return ""

            dialog_pairs: List[Dict[str, str]] = []
            sorted_messages = human_dialog_timeline(message_data_list)

            for i in range(len(sorted_messages) - 1):
                current_msg = sorted_messages[i]
                next_msg = sorted_messages[i + 1]

                pairs = extract_human_dialog_pairs([current_msg, next_msg], group_id)
                if not pairs:
                    continue
                context_text = pairs[0]["situation"]
                response_text = pairs[0]["expression"]

                # Basic length / trivial-content filter
                if (
                    len(context_text) < 5
                    or len(response_text) < 5
                ):
                    continue

                # Filter duplicate / contained content
                if (
                    context_text in response_text
                    or response_text in context_text
                ):
                    logger.debug(
                        f"过滤重复内容: A='{context_text[:30]}...' B='{response_text[:30]}...'"
                    )
                    continue

                if await self.is_valid_dialog_pair(current_msg, next_msg, group_id):
                    dialog_pairs.append({"context": context_text, "response": response_text})

            if len(dialog_pairs) >= 3:
                selected_pairs = dialog_pairs[:5]
                few_shots_lines = [
                    "*Here are few shots of dialogs, you need to imitate "
                    "the tone of 'B' in the following dialogs to respond:"
                ]
                for pair in selected_pairs:
                    few_shots_lines.append(f"A: {pair['context']}")
                    few_shots_lines.append(f"B: {pair['response']}")

                logger.info(
                    f"群组 {group_id} 生成了 {len(selected_pairs)} 组Few Shots对话"
                )
                return "\n".join(few_shots_lines)

            logger.debug(
                f"群组 {group_id} 未找到足够的有效对话片段"
                f"（需要至少3组，当前{len(dialog_pairs)}组）"
            )
            return ""

        except Exception as e:
            logger.error(f"生成Few Shots对话失败: {e}")
            return ""

    # Dialog-pair validation

    @monitored
    async def is_valid_dialog_pair(
        self, msg1: Any, msg2: Any, group_id: str
    ) -> bool:
        """Determine whether two messages form a genuine dialog pair.

        Uses the professional ``MessageRelationshipAnalyzer`` when available,
        falling back to validated human adjacency otherwise.
        """
        try:
            pairs = extract_human_dialog_pairs([msg1, msg2], group_id)
            if not pairs or pairs[0]["context_sender_id"] != str(
                message_value(msg1, "sender_id", "")
            ).strip():
                return False
            if (
                not self._factory_manager
                or not hasattr(self._factory_manager, "_service_factory")
                or not self._factory_manager._service_factory
            ):
                return True

            relationship_analyzer = (
                self._factory_manager.get_service_factory()
                .create_message_relationship_analyzer()
            )
            if not relationship_analyzer:
                return True

            msg1_dict = {
                "message_id": message_value(msg1, "message_id")
                or str(hash(f"{message_timestamp(msg1)}{message_value(msg1, 'sender_id')}")),
                "sender_id": message_value(msg1, "sender_id"),
                "message": pairs[0]["situation"],
                "timestamp": message_timestamp(msg1) or 0,
            }
            msg2_dict = {
                "message_id": message_value(msg2, "message_id")
                or str(hash(f"{message_timestamp(msg2)}{message_value(msg2, 'sender_id')}")),
                "sender_id": message_value(msg2, "sender_id"),
                "message": pairs[0]["expression"],
                "timestamp": message_timestamp(msg2) or 0,
            }

            relationship = await relationship_analyzer._analyze_message_pair(
                msg1_dict, msg2_dict, group_id
            )

            if relationship:
                is_valid = (
                    relationship.relationship_type
                    in ("direct_reply", "topic_continuation")
                    and relationship.confidence > 0.5
                )
                if is_valid:
                    logger.debug(
                        f"识别对话关系: {relationship.relationship_type} "
                        f"(置信度: {relationship.confidence:.2f})"
                    )
                return is_valid

            return False

        except Exception as e:
            logger.error(f"消息关系判断失败: {e}", exc_info=True)
            return False

    # Style-learning review management

    @monitored
    async def create_style_learning_review_request(
        self,
        group_id: str,
        learned_patterns: List[Any],
        few_shots_content: str,
    ) -> None:
        """Create a review request for learned dialog-style patterns.

        Skips creation when an identical pending review already exists
        (de-duplication).
        """
        try:
            existing_reviews = await self.get_pending_style_reviews(group_id)
            if existing_reviews:
                for existing in existing_reviews:
                    if existing.get("few_shots_content", "") == few_shots_content:
                        logger.info(
                            f"群组 {group_id} 已存在相同的待审查风格学习记录，跳过重复创建"
                        )
                        return

            review_data = {
                "type": UPDATE_TYPE_STYLE_LEARNING,
                "group_id": group_id,
                "timestamp": time.time(),
                "learned_patterns": [p.to_dict() for p in learned_patterns],
                "few_shots_content": few_shots_content,
                "status": "pending",
                "description": (
                    f"群组 {group_id} 的对话风格学习结果"
                    f"（包含 {len(learned_patterns)} 个表达模式）"
                ),
            }

            await self._db_manager.create_style_learning_review(review_data)
            logger.info(f"对话风格学习审查请求已创建: {group_id}")

        except Exception as e:
            logger.error(f"创建对话风格学习审查请求失败: {e}")

    async def get_pending_style_reviews(
        self, group_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve pending style-learning review records for a group."""
        try:
            async with self._db_manager.get_session() as session:
                from sqlalchemy import select, desc
                from ...models.orm.learning import StyleLearningReview

                stmt = (
                    select(StyleLearningReview)
                    .where(
                        StyleLearningReview.group_id == group_id,
                        StyleLearningReview.status == 'pending',
                    )
                    .order_by(desc(StyleLearningReview.timestamp))
                    .limit(10)
                )
                result = await session.execute(stmt)
                reviews = result.scalars().all()
                return [
                    {
                        "id": r.id,
                        "group_id": r.group_id,
                        "few_shots_content": r.few_shots_content,
                        "timestamp": r.timestamp,
                    }
                    for r in reviews
                ]

        except Exception as e:
            logger.error(f"获取待审查风格学习记录失败: {e}")
            return []
