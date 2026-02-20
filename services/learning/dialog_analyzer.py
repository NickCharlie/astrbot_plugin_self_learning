"""Few-shot dialog generation, dialog-pair validation, and style review management.

Extracted from main.py to encapsulate dialog analysis logic used during
expression-style learning.
"""

import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger


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

    # ------------------------------------------------------------------
    # Few-shot dialog generation
    # ------------------------------------------------------------------

    async def generate_few_shots_dialog(
        self, group_id: str, message_data_list: List[Any]
    ) -> str:
        """Generate few-shot dialog content from collected messages.

        Requires at least 10 messages and 3 valid dialog pairs to produce
        output.  Returns an empty string when the threshold is not met.
        """
        try:
            if len(message_data_list) < 10:
                logger.debug(
                    f"群组 {group_id} 消息数量不足10条"
                    f"（当前{len(message_data_list)}条），跳过Few Shots生成"
                )
                return ""

            dialog_pairs: List[Dict[str, str]] = []
            sorted_messages = sorted(message_data_list, key=lambda x: x.timestamp)

            for i in range(len(sorted_messages) - 1):
                current_msg = sorted_messages[i]
                next_msg = sorted_messages[i + 1]

                # Skip consecutive messages from the same sender
                if current_msg.sender_id == next_msg.sender_id:
                    continue

                user_msg = current_msg.message.strip()
                bot_response = next_msg.message.strip()

                # Basic length / trivial-content filter
                if (
                    len(user_msg) < 5
                    or len(bot_response) < 5
                    or user_msg in ("？", "？？", "...", "。。。")
                    or bot_response in ("？", "？？", "...", "。。。")
                ):
                    continue

                # Filter duplicate / contained content
                if (
                    user_msg == bot_response
                    or user_msg in bot_response
                    or bot_response in user_msg
                ):
                    logger.debug(
                        f"过滤重复内容: A='{user_msg[:30]}...' B='{bot_response[:30]}...'"
                    )
                    continue

                if await self.is_valid_dialog_pair(current_msg, next_msg, group_id):
                    dialog_pairs.append({"user": user_msg, "assistant": bot_response})

            if len(dialog_pairs) >= 3:
                selected_pairs = dialog_pairs[:5]
                few_shots_lines = [
                    "*Here are few shots of dialogs, you need to imitate "
                    "the tone of 'B' in the following dialogs to respond:"
                ]
                for pair in selected_pairs:
                    few_shots_lines.append(f"A: {pair['user']}")
                    few_shots_lines.append(f"B: {pair['assistant']}")

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

    # ------------------------------------------------------------------
    # Dialog-pair validation
    # ------------------------------------------------------------------

    async def is_valid_dialog_pair(
        self, msg1: Any, msg2: Any, group_id: str
    ) -> bool:
        """Determine whether two messages form a genuine dialog pair.

        Uses the professional ``MessageRelationshipAnalyzer`` when available,
        falling back to a simple inequality check otherwise.
        """
        try:
            if (
                not self._factory_manager
                or not hasattr(self._factory_manager, "_service_factory")
                or not self._factory_manager._service_factory
            ):
                return msg1.message != msg2.message

            relationship_analyzer = (
                self._factory_manager.get_service_factory()
                .create_message_relationship_analyzer()
            )
            if not relationship_analyzer:
                return msg1.message != msg2.message

            msg1_dict = {
                "message_id": msg1.message_id
                or str(hash(f"{msg1.timestamp}{msg1.sender_id}")),
                "sender_id": msg1.sender_id,
                "message": msg1.message,
                "timestamp": msg1.timestamp,
            }
            msg2_dict = {
                "message_id": msg2.message_id
                or str(hash(f"{msg2.timestamp}{msg2.sender_id}")),
                "sender_id": msg2.sender_id,
                "message": msg2.message,
                "timestamp": msg2.timestamp,
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

    # ------------------------------------------------------------------
    # Style-learning review management
    # ------------------------------------------------------------------

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
                "type": "style_learning",
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
            async with self._db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    """
                    SELECT id, group_id, few_shots_content, timestamp
                    FROM style_learning_reviews
                    WHERE group_id = ? AND status = 'pending'
                      AND type = 'style_learning'
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """,
                    (group_id,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "group_id": row[1],
                        "few_shots_content": row[2],
                        "timestamp": row[3],
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取待审查风格学习记录失败: {e}")
            return []
