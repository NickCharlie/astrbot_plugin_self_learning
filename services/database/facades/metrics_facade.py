"""
指标聚合 Facade — 跨域统计指标的业务入口
"""
import time
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade


class MetricsFacade(BaseFacade):
    """跨域指标聚合 Facade"""

    async def get_group_statistics(self, group_id: str = None) -> Dict[str, Any]:
        """获取群组综合统计数据"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func, and_
                from ....models.orm.message import RawMessage, FilteredMessage
                from ....models.orm.learning import PersonaLearningReview, StyleLearningReview

                # 原始消息数
                raw_stmt = select(func.count()).select_from(RawMessage)
                if group_id:
                    raw_stmt = raw_stmt.where(RawMessage.group_id == group_id)
                raw_count = (await session.execute(raw_stmt)).scalar() or 0

                # 筛选消息数
                filtered_stmt = select(func.count()).select_from(FilteredMessage)
                if group_id:
                    filtered_stmt = filtered_stmt.where(FilteredMessage.group_id == group_id)
                filtered_count = (await session.execute(filtered_stmt)).scalar() or 0

                # 人格学习审核数
                persona_stmt = select(func.count()).select_from(PersonaLearningReview)
                if group_id:
                    persona_stmt = persona_stmt.where(PersonaLearningReview.group_id == group_id)
                persona_count = (await session.execute(persona_stmt)).scalar() or 0

                # 风格学习审核数
                style_stmt = select(func.count()).select_from(StyleLearningReview)
                if group_id:
                    style_stmt = style_stmt.where(StyleLearningReview.group_id == group_id)
                style_count = (await session.execute(style_stmt)).scalar() or 0

                return {
                    'raw_messages': raw_count,
                    'filtered_messages': filtered_count,
                    'persona_reviews': persona_count,
                    'style_reviews': style_count,
                    'group_id': group_id,
                }
        except Exception as e:
            self._logger.error(f"[MetricsFacade] 获取群组统计失败: {e}")
            return {
                'raw_messages': 0, 'filtered_messages': 0,
                'persona_reviews': 0, 'style_reviews': 0,
                'group_id': group_id,
            }

    async def get_detailed_metrics(self, group_id: str = None) -> Dict[str, Any]:
        """获取详细指标"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.message import RawMessage, FilteredMessage, BotMessage
                from ....models.orm.learning import (
                    PersonaLearningReview, StyleLearningReview,
                    LearningBatch, StyleLearningPattern
                )

                async def _count(model, group_col=None):
                    stmt = select(func.count()).select_from(model)
                    if group_id and group_col is not None:
                        stmt = stmt.where(group_col == group_id)
                    return (await session.execute(stmt)).scalar() or 0

                raw = await _count(RawMessage, RawMessage.group_id)
                filtered = await _count(FilteredMessage, FilteredMessage.group_id)
                bot = await _count(BotMessage, BotMessage.group_id)
                persona_reviews = await _count(PersonaLearningReview, PersonaLearningReview.group_id)
                style_reviews = await _count(StyleLearningReview, StyleLearningReview.group_id)
                batches = await _count(LearningBatch, LearningBatch.group_id)
                patterns = await _count(StyleLearningPattern, StyleLearningPattern.group_id)

                return {
                    'messages': {
                        'raw': raw, 'filtered': filtered, 'bot': bot,
                    },
                    'learning': {
                        'persona_reviews': persona_reviews,
                        'style_reviews': style_reviews,
                        'batches': batches,
                        'style_patterns': patterns,
                    },
                    'group_id': group_id,
                }
        except Exception as e:
            self._logger.error(f"[MetricsFacade] 获取详细指标失败: {e}")
            return {
                'messages': {'raw': 0, 'filtered': 0, 'bot': 0},
                'learning': {
                    'persona_reviews': 0, 'style_reviews': 0,
                    'batches': 0, 'style_patterns': 0,
                },
                'group_id': group_id,
            }

    async def get_trends_data(self) -> Dict[str, Any]:
        """获取趋势数据"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.message import RawMessage
                from ....models.orm.learning import LearningBatch

                # 过去7天每天的消息数
                cutoff = int(time.time()) - (7 * 24 * 3600)
                msg_stmt = (
                    select(RawMessage)
                    .where(RawMessage.timestamp >= cutoff)
                    .order_by(RawMessage.timestamp)
                )
                msg_result = await session.execute(msg_stmt)
                messages = msg_result.scalars().all()

                daily: Dict[str, int] = {}
                for m in messages:
                    day = time.strftime('%Y-%m-%d', time.localtime(m.timestamp))
                    daily[day] = daily.get(day, 0) + 1

                # 最近的学习批次
                batch_stmt = (
                    select(LearningBatch)
                    .order_by(LearningBatch.start_time.desc())
                    .limit(10)
                )
                batch_result = await session.execute(batch_stmt)
                batches = [self._row_to_dict(b) for b in batch_result.scalars().all()]

                return {
                    'daily_messages': daily,
                    'recent_batches': batches,
                }
        except Exception as e:
            self._logger.error(f"[MetricsFacade] 获取趋势数据失败: {e}")
            return {'daily_messages': {}, 'recent_batches': []}
