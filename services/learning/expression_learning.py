"""Expression learning module.

Owns expression/few-shot learning persistence so progressive learning can
orchestrate batches without also carrying expression-specific storage rules.
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List

from astrbot.api import logger

from ...constants import UPDATE_TYPE_STYLE_LEARNING
from ...utils.persona_selection import normalize_persona_scope
from .conversation_samples import (
    encode_style_samples,
    extract_human_dialog_pairs,
    is_human_learning_message,
    sanitize_style_sample,
)
from .sample_filter import should_ignore_learning_sample


class ExpressionLearningModule:
    """Persist learned expression patterns and style review records."""

    def __init__(self, db_manager: Any, config: Any = None) -> None:
        self.db_manager = db_manager
        self.config = config

    async def save_style_learning_record(
        self,
        group_id: str,
        style_analysis: Any,
        messages: List[Dict[str, Any]],
        quality_metrics: Any = None,
        persona_id: str = "default",
    ) -> None:
        """Save expression learning output and create a style review record."""
        try:
            timeline = list(messages or [])
            messages = [
                message for message in timeline
                if is_human_learning_message(message, group_id)
            ]
            persona_id = normalize_persona_scope(persona_id)

            if style_analysis and hasattr(style_analysis, "data"):
                style_analysis_dict = style_analysis.data
            elif isinstance(style_analysis, dict):
                style_analysis_dict = style_analysis
            else:
                style_analysis_dict = {}
            if not isinstance(style_analysis_dict, dict):
                style_analysis_dict = {}

            if not style_analysis_dict and not messages:
                logger.debug(
                    f"群组 {group_id} 没有风格分析结果且没有消息，跳过风格学习记录保存"
                )
                return

            # Model summaries do not necessarily contain expression_patterns.
            # Ground automatic samples in human turns, never generated bot text.
            if timeline:
                expression_patterns = extract_human_dialog_pairs(timeline, group_id)
            else:
                expression_patterns = self.filter_expression_patterns(
                    style_analysis_dict.get("expression_patterns", [])
                )
            expression_patterns = [
                pattern for pattern in expression_patterns
                if str(pattern.get("group_id") or group_id) == str(group_id)
            ]
            user_scope_enabled = bool(
                getattr(self.config, "enable_expression_user_scope", False)
            )
            expression_patterns = [
                {
                    **pattern,
                    "group_id": str(group_id),
                    "persona_id": persona_id,
                    "user_id": (
                        str(pattern.get("user_id") or pattern.get("sender_id") or "").strip() or None
                        if user_scope_enabled else None
                    ),
                }
                for pattern in expression_patterns
            ]

            if expression_patterns:
                await self.save_expression_patterns(
                    group_id,
                    expression_patterns,
                    persona_id=persona_id,
                )

            few_shots_content = ""
            if expression_patterns:
                few_shots_content = self.build_few_shots_from_patterns(
                    expression_patterns
                )

            if not few_shots_content and messages:
                few_shots_content = f"基于 {len(messages)} 条对话消息的风格学习"

            learned_patterns = []
            for pattern in expression_patterns[:10]:
                learned_patterns.append(
                    {
                        "situation": pattern.get("situation", ""),
                        "expression": pattern.get("expression", ""),
                        "weight": pattern.get("weight", 1.0),
                        "confidence": pattern.get("confidence", 0.8),
                        "group_id": pattern.get("group_id", group_id),
                        "persona_id": persona_id,
                        "user_id": pattern.get("user_id"),
                    }
                )

            confidence_score = (
                quality_metrics.consistency_score
                if quality_metrics and hasattr(quality_metrics, "consistency_score")
                else 0.75
            )
            del confidence_score  # Stored review currently derives status from patterns.

            pattern_count = len(expression_patterns)
            message_count = len(messages) if messages else 0
            description = (
                f"群组 {group_id} 的对话风格学习结果"
                f"（处理 {message_count} 条消息，提取 {pattern_count} 个表达模式）"
            )

            try:
                async with self.db_manager.get_session() as session:
                    from ...models.orm.learning import StyleLearningReview

                    current_timestamp = time.time()
                    has_patterns = bool(learned_patterns)

                    review = StyleLearningReview(
                        type=UPDATE_TYPE_STYLE_LEARNING,
                        group_id=group_id,
                        timestamp=current_timestamp,
                        learned_patterns=json.dumps(
                            learned_patterns, ensure_ascii=False
                        ),
                        few_shots_content=few_shots_content,
                        metadata_=json.dumps({
                            "persona_id": persona_id,
                            "user_ids": sorted({
                                pattern["user_id"] for pattern in learned_patterns
                                if pattern.get("user_id")
                            }),
                        }, ensure_ascii=False),
                        status="pending" if has_patterns else "approved",
                        description=description,
                        reviewer_comment=None if has_patterns else "自动批准（无有效对话对）",
                        review_time=None if has_patterns else current_timestamp,
                        created_at=datetime.fromtimestamp(current_timestamp),
                        updated_at=datetime.fromtimestamp(current_timestamp),
                    )

                    session.add(review)
                    await session.commit()
                    await session.refresh(review)

                    logger.info(
                        f" 对话风格学习记录已保存 (ID: {review.id})，"
                        f"处理 {message_count} 条消息，提取 {pattern_count} 个模式"
                    )

            except Exception as exc:
                logger.error(f"保存对话风格学习记录失败: {exc}", exc_info=True)

        except Exception as exc:
            logger.error(f"保存风格学习记录失败: {exc}", exc_info=True)

    @staticmethod
    def filter_expression_patterns(
        patterns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove command/system-derived pairs before saving style samples."""
        filtered = []
        for pattern in patterns or []:
            if not isinstance(pattern, dict):
                continue
            situation = pattern.get("situation", "")
            expression = pattern.get("expression", "")
            if not isinstance(situation, str) or not isinstance(expression, str):
                continue
            if should_ignore_learning_sample(situation):
                continue
            if should_ignore_learning_sample(expression):
                continue
            if str(pattern.get("sender_id", "")).strip().lower() in {"bot", "assistant"}:
                continue
            filtered.append({
                **pattern,
                "situation": sanitize_style_sample(situation),
                "expression": sanitize_style_sample(expression),
            })
        return filtered

    @classmethod
    def build_few_shots_from_patterns(cls, patterns: List[Dict[str, Any]]) -> str:
        """Build few-shot dialog text from expression patterns."""
        pairs = [
            pattern for pattern in cls.filter_expression_patterns(patterns)[:5]
            if pattern.get("situation") and pattern.get("expression")
        ]
        if not pairs:
            return ""
        return encode_style_samples(pairs)

    async def merge_bot_messages_for_pairs(
        self, group_id: str, user_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compatibility shim: preserve the supplied timeline without bot lookups."""
        return list(user_messages or [])

    @staticmethod
    def extract_fewshot_pairs_from_merged(
        merged: List[Dict[str, Any]], group_id: str
    ) -> List[Dict[str, Any]]:
        """Compatibility entry point for source-grounded human dialog pairs."""
        return extract_human_dialog_pairs(merged, group_id)

    async def save_expression_patterns(
        self,
        group_id: str,
        patterns: List[Dict[str, Any]],
        persona_id: str = "default",
    ) -> None:
        """Save expression patterns to the expression_patterns table."""
        try:
            if not patterns:
                return
            persona_id = normalize_persona_scope(persona_id)

            async with self.db_manager.get_session() as session:
                from ...models.orm.expression import ExpressionPattern

                current_time = time.time()
                objects = []

                for pattern in self.filter_expression_patterns(patterns):
                    if str(pattern.get("group_id") or group_id) != str(group_id):
                        continue
                    situation = pattern.get("situation", "").strip()
                    expression = pattern.get("expression", "").strip()

                    if not situation or not expression:
                        continue

                    objects.append(
                        ExpressionPattern(
                            group_id=group_id,
                            persona_id=persona_id,
                            user_id=pattern.get("user_id"),
                            situation=situation,
                            expression=expression,
                            weight=float(pattern.get("weight", 1.0)),
                            last_active_time=current_time,
                            create_time=current_time,
                        )
                    )

                if objects:
                    session.add_all(objects)
                    await session.commit()
                    logger.info(
                        f"已保存 {len(objects)} 个表达模式到数据库 (群组: {group_id})"
                    )

        except Exception as exc:
            logger.error(f"保存表达模式失败: {exc}", exc_info=True)
