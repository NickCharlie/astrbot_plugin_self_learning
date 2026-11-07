"""
学习内容浏览服务 - 学习内容四分类（对话/分析/特征/历史）与学习批次分页。

独立 WebUI 蓝图（/api/style_learning/content_text、/api/batches）与内嵌插件页
桥接（core.page_api 的 page/content、page/style、page/batches）共用本服务，
保证两端「学习内容 / 表达样本库 / 最近学习批次」读到同一份数据。
"""
import json
import time
from datetime import datetime
from typing import Any, Dict, List

from astrbot.api import logger

CONTENT_BUCKETS = ('dialogues', 'analysis', 'features', 'history')


def _clamp_quality_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _optional_float(value):
    if value is None:
        return None
    try:
        return _clamp_quality_score(value)
    except (TypeError, ValueError):
        return None


def _non_negative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def effective_batch_quality(batch, max_batch_size=200) -> float:
    """Return stored quality, or a conservative display fallback for legacy zero rows."""
    stored_quality = _optional_float(getattr(batch, 'quality_score', None))
    if stored_quality is not None and stored_quality > 0:
        return stored_quality

    if getattr(batch, 'success', None) is False:
        return stored_quality if stored_quality is not None else 0.0

    processed = max(
        _non_negative_int(getattr(batch, 'processed_messages', 0)),
        _non_negative_int(getattr(batch, 'message_count', 0)),
    )
    filtered = _non_negative_int(getattr(batch, 'filtered_count', 0))
    if processed <= 0 and filtered <= 0:
        return stored_quality if stored_quality is not None else 0.0

    try:
        batch_size = max(1, int(max_batch_size or 200))
    except (TypeError, ValueError):
        batch_size = 200

    volume_score = min(processed / batch_size, 1.0)
    filtered_score = min(filtered / max(processed, filtered, 1), 1.0) if filtered else 0.0
    success_score = 0.10 if getattr(batch, 'success', True) else 0.0
    return _clamp_quality_score(0.25 + (volume_score * 0.45) + (filtered_score * 0.20) + success_score)


def _format_ts(value) -> str:
    if not value:
        return ''
    return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')


def _parse_json(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _orm_models():
    try:
        from ...models.orm import (
            ExpressionPattern, LearningBatch, RawMessage, StyleLearningReview,
        )
    except ImportError:
        from models.orm import (
            ExpressionPattern, LearningBatch, RawMessage, StyleLearningReview,
        )
    return RawMessage, StyleLearningReview, ExpressionPattern, LearningBatch


class LearningContentService:
    """学习内容与学习批次读取服务"""

    def __init__(self, container):
        self.container = container
        self.database_manager = getattr(container, 'database_manager', None)

    def _max_batch_size(self) -> int:
        config = getattr(self.container, 'plugin_config', None)
        if isinstance(config, dict):
            value = config.get('max_messages_per_batch', 200)
        else:
            value = getattr(config, 'max_messages_per_batch', 200)
        try:
            return max(1, int(value or 200))
        except (TypeError, ValueError):
            return 200

    def _has_session(self) -> bool:
        return bool(self.database_manager) and hasattr(self.database_manager, 'get_session')

    async def get_content_text(self, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """读取学习内容四分类：最近原始对话、风格分析、表达模式与学习批次。"""
        content_data: Dict[str, List[Dict[str, Any]]] = {bucket: [] for bucket in CONTENT_BUCKETS}
        if not self._has_session():
            return content_data

        from sqlalchemy import desc, select

        RawMessage, StyleLearningReview, ExpressionPattern, LearningBatch = _orm_models()
        max_batch_size = self._max_batch_size()

        try:
            async with self.database_manager.get_session() as session:
                # 1. dialogues — 最近的原始消息
                stmt = select(RawMessage).order_by(desc(RawMessage.timestamp)).limit(limit)
                result = await session.execute(stmt)
                for msg in result.scalars().all():
                    message_text = msg.message if msg.message else ''
                    if len(message_text.strip()) < 5:
                        continue
                    content_data['dialogues'].append({
                        'id': msg.id,
                        'type': 'dialogue',
                        'title': msg.sender_name or msg.sender_id or '未知发送者',
                        'timestamp': _format_ts(msg.timestamp if msg.timestamp else time.time()),
                        'text': f"{msg.sender_name or msg.sender_id}: {message_text}",
                        'detail': message_text,
                        'metadata': f"群组: {msg.group_id}, 平台: {msg.platform or '未知'}",
                        'raw': {
                            'sender_id': msg.sender_id,
                            'sender_name': msg.sender_name,
                            'group_id': msg.group_id,
                            'platform': msg.platform,
                            'message_id': getattr(msg, 'message_id', None),
                            'reply_to': getattr(msg, 'reply_to', None),
                            'processed': bool(getattr(msg, 'processed', False)),
                        },
                    })

                # 2. analysis — 已审批 / 待审的风格学习分析结果
                analysis_stmt = (
                    select(StyleLearningReview)
                    .where(StyleLearningReview.status.in_(['approved', 'pending']))
                    .order_by(desc(StyleLearningReview.timestamp))
                    .limit(limit)
                )
                analysis_result = await session.execute(analysis_stmt)
                for review in analysis_result.scalars().all():
                    patterns = _parse_json(review.learned_patterns, [])
                    few_shots_content = review.few_shots_content or ''
                    description = review.description or ''
                    content_data['analysis'].append({
                        'id': review.id,
                        'type': review.type or 'style_learning',
                        'title': description or f"风格学习 ({review.type})",
                        'timestamp': _format_ts(review.timestamp),
                        'text': description or few_shots_content or f"风格学习 ({review.type})",
                        'detail': few_shots_content or description,
                        'status': review.status,
                        'patterns': patterns,
                        'metadata': f"群组: {review.group_id}, 状态: {review.status}, 模式数: {len(patterns) if isinstance(patterns, list) else 0}",
                        'raw': {
                            'group_id': review.group_id,
                            'reviewer_comment': review.reviewer_comment,
                            'review_time': review.review_time,
                            'created_at': review.created_at.isoformat() if review.created_at else None,
                            'updated_at': review.updated_at.isoformat() if review.updated_at else None,
                        },
                    })

                # 3. features — 已学习的表达模式
                features_stmt = (
                    select(ExpressionPattern)
                    .order_by(desc(ExpressionPattern.last_active_time))
                    .limit(limit)
                )
                features_result = await session.execute(features_stmt)
                for pattern in features_result.scalars().all():
                    weight = pattern.weight if pattern.weight is not None else 0
                    content_data['features'].append({
                        'id': pattern.id,
                        'type': 'expression_pattern',
                        'title': pattern.situation,
                        'timestamp': _format_ts(pattern.last_active_time),
                        'text': f"场景: {pattern.situation}\n表达: {pattern.expression}",
                        'detail': pattern.expression,
                        'metadata': f"群组: {pattern.group_id}, 权重: {weight:.2f}",
                        'raw': {
                            'group_id': pattern.group_id,
                            'situation': pattern.situation,
                            'expression': pattern.expression,
                            'weight': weight,
                            'create_time': pattern.create_time,
                            'last_active_time': pattern.last_active_time,
                        },
                    })

                # 4. history — 学习批次历史
                history_stmt = (
                    select(LearningBatch)
                    .order_by(desc(LearningBatch.start_time))
                    .limit(limit)
                )
                history_result = await session.execute(history_stmt)
                for batch in history_result.scalars().all():
                    quality_score = effective_batch_quality(batch, max_batch_size)
                    duration = ''
                    if batch.start_time and batch.end_time:
                        duration = f", 耗时: {batch.end_time - batch.start_time:.1f}s"
                    content_data['history'].append({
                        'id': batch.id,
                        'type': 'learning_batch',
                        'title': batch.batch_name or batch.batch_id or '学习批次',
                        'timestamp': _format_ts(batch.start_time),
                        'text': f"批次: {batch.batch_name or batch.batch_id}, 质量: {quality_score:.3f}",
                        'detail': batch.error_message or f"状态: {batch.status or 'unknown'}",
                        'status': batch.status,
                        'metadata': f"群组: {batch.group_id}, 消息: {batch.processed_messages or 0}, 成功: {'是' if batch.success else '否'}{duration}",
                        'raw': {
                            'batch_id': batch.batch_id,
                            'batch_name': batch.batch_name,
                            'group_id': batch.group_id,
                            'start_time': batch.start_time,
                            'end_time': batch.end_time,
                            'quality_score': quality_score,
                            'raw_quality_score': batch.quality_score,
                            'processed_messages': batch.processed_messages,
                            'message_count': batch.message_count,
                            'filtered_count': batch.filtered_count,
                            'success': batch.success,
                            'error_message': batch.error_message,
                            'status': batch.status,
                        },
                    })
        except Exception as e:
            logger.warning(f"获取学习内容文本失败: {e}")

        return content_data

    async def list_batches(self, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """分页读取学习批次（按开始时间倒序）。数据库不可用时抛出 ValueError。"""
        page = max(1, int(page or 1))
        page_size = max(1, min(100, int(page_size or 10)))
        if not self._has_session():
            raise ValueError('数据库管理器未初始化')

        from sqlalchemy import desc, func, select

        _, _, _, LearningBatch = _orm_models()
        max_batch_size = self._max_batch_size()

        async with self.database_manager.get_session() as session:
            total = (await session.execute(select(func.count()).select_from(LearningBatch))).scalar() or 0
            stmt = (
                select(LearningBatch)
                .order_by(desc(LearningBatch.start_time))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await session.execute(stmt)
            batches = [
                {
                    'id': batch.id,
                    'batch_id': batch.batch_id,
                    'batch_name': batch.batch_name,
                    'group_id': batch.group_id,
                    'start_time': batch.start_time,
                    'end_time': batch.end_time,
                    'quality_score': effective_batch_quality(batch, max_batch_size),
                    'raw_quality_score': batch.quality_score,
                    'processed_messages': batch.processed_messages,
                    'message_count': batch.message_count,
                    'filtered_count': batch.filtered_count,
                    'success': batch.success,
                    'status': batch.status,
                    'error_message': batch.error_message,
                }
                for batch in result.scalars().all()
            ]

        return {
            'batches': batches,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total + page_size - 1) // page_size),
        }
