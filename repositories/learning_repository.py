"""
学习系统相关的 Repository
提供人格学习和风格学习的数据访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from typing import List, Optional, Dict, Any
from astrbot.api import logger
import time

from .base_repository import BaseRepository
from ..models.orm import (
    PersonaLearningReview,
    StyleLearningReview,
    StyleLearningPattern,
    InteractionRecord
)


class PersonaLearningReviewRepository(BaseRepository[PersonaLearningReview]):
    """人格学习审核 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PersonaLearningReview)

    async def get_pending_reviews(self, limit: int = 50) -> List[PersonaLearningReview]:
        """
        获取待审查的人格学习更新

        Args:
            limit: 最大返回数量

        Returns:
            List[PersonaLearningReview]: 待审查列表
        """
        try:
            stmt = select(PersonaLearningReview).where(
                PersonaLearningReview.status == 'pending'
            ).order_by(
                desc(PersonaLearningReview.timestamp)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PersonaLearningReviewRepository] 获取待审查记录失败: {e}")
            return []

    async def get_reviewed_updates(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[PersonaLearningReview]:
        """
        获取已审查的人格学习更新

        Args:
            limit: 最大返回数量
            offset: 偏移量
            status_filter: 状态过滤（approved/rejected）

        Returns:
            List[PersonaLearningReview]: 已审查列表
        """
        try:
            stmt = select(PersonaLearningReview)

            # 状态过滤
            if status_filter:
                stmt = stmt.where(PersonaLearningReview.status == status_filter)
            else:
                stmt = stmt.where(
                    or_(
                        PersonaLearningReview.status == 'approved',
                        PersonaLearningReview.status == 'rejected'
                    )
                )

            stmt = stmt.order_by(
                desc(PersonaLearningReview.review_time)
            ).offset(offset).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PersonaLearningReviewRepository] 获取已审查记录失败: {e}")
            return []

    async def approve_review(
        self,
        review_id: int,
        reviewer_comment: Optional[str] = None
    ) -> bool:
        """
        批准人格学习审核

        Args:
            review_id: 审核 ID
            reviewer_comment: 审核评论

        Returns:
            bool: 是否成功
        """
        try:
            current_time = int(time.time())
            return await self.update_by_id(
                review_id,
                status='approved',
                reviewer_comment=reviewer_comment,
                review_time=current_time,
                updated_at=current_time
            )
        except Exception as e:
            logger.error(f"[PersonaLearningReviewRepository] 批准审核失败: {e}")
            return False

    async def reject_review(
        self,
        review_id: int,
        reviewer_comment: Optional[str] = None
    ) -> bool:
        """
        拒绝人格学习审核

        Args:
            review_id: 审核 ID
            reviewer_comment: 审核评论

        Returns:
            bool: 是否成功
        """
        try:
            current_time = int(time.time())
            return await self.update_by_id(
                review_id,
                status='rejected',
                reviewer_comment=reviewer_comment,
                review_time=current_time,
                updated_at=current_time
            )
        except Exception as e:
            logger.error(f"[PersonaLearningReviewRepository] 拒绝审核失败: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取人格学习统计

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 1. 统计不同更新类型数量
            unique_types_stmt = select(func.count(func.distinct(PersonaLearningReview.update_type)))
            unique_types_result = await self.session.execute(unique_types_stmt)
            unique_types = unique_types_result.scalar() or 0

            # 2. 计算平均置信度
            avg_confidence_stmt = select(func.avg(PersonaLearningReview.confidence_score))
            avg_confidence_result = await self.session.execute(avg_confidence_stmt)
            avg_confidence = avg_confidence_result.scalar() or 0.0

            # 3. 统计总记录数
            total_stmt = select(func.count()).select_from(PersonaLearningReview)
            total_result = await self.session.execute(total_stmt)
            total_count = total_result.scalar() or 0

            # 4. 统计各状态数量
            approved_stmt = select(func.count()).select_from(PersonaLearningReview).where(
                PersonaLearningReview.status == 'approved'
            )
            approved_result = await self.session.execute(approved_stmt)
            approved_count = approved_result.scalar() or 0

            rejected_stmt = select(func.count()).select_from(PersonaLearningReview).where(
                PersonaLearningReview.status == 'rejected'
            )
            rejected_result = await self.session.execute(rejected_stmt)
            rejected_count = rejected_result.scalar() or 0

            pending_stmt = select(func.count()).select_from(PersonaLearningReview).where(
                PersonaLearningReview.status == 'pending'
            )
            pending_result = await self.session.execute(pending_stmt)
            pending_count = pending_result.scalar() or 0

            # 5. 最后更新时间
            last_update_stmt = select(func.max(PersonaLearningReview.timestamp))
            last_update_result = await self.session.execute(last_update_stmt)
            latest_update = last_update_result.scalar()

            return {
                "total": total_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "pending": pending_count,
                "unique_types": unique_types,
                "avg_confidence": round(float(avg_confidence), 2) if avg_confidence else 0.0,
                "latest_update": latest_update
            }

        except Exception as e:
            logger.error(f"[PersonaLearningReviewRepository] 获取统计数据失败: {e}")
            return {
                "total": 0,
                "approved": 0,
                "rejected": 0,
                "pending": 0,
                "unique_types": 0,
                "avg_confidence": 0.0,
                "latest_update": None
            }


class StyleLearningReviewRepository(BaseRepository[StyleLearningReview]):
    """风格学习审核 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, StyleLearningReview)

    async def get_pending_reviews(self, limit: int = 50) -> List[StyleLearningReview]:
        """
        获取待审查的风格学习更新

        Args:
            limit: 最大返回数量

        Returns:
            List[StyleLearningReview]: 待审查列表
        """
        try:
            stmt = select(StyleLearningReview).where(
                StyleLearningReview.status == 'pending'
            ).order_by(
                desc(StyleLearningReview.timestamp)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[StyleLearningReviewRepository] 获取待审查记录失败: {e}")
            return []

    async def update_review_status(
        self,
        review_id: int,
        status: str,
        reviewer_comment: Optional[str] = None
    ) -> bool:
        """
        更新风格审查状态

        Args:
            review_id: 审核 ID
            status: 新状态（approved/rejected）
            reviewer_comment: 审核评论

        Returns:
            bool: 是否成功
        """
        try:
            current_time = int(time.time())
            return await self.update_by_id(
                review_id,
                status=status,
                reviewer_comment=reviewer_comment,
                review_time=current_time,
                updated_at=current_time
            )
        except Exception as e:
            logger.error(f"[StyleLearningReviewRepository] 更新审核状态失败: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取风格学习统计

        Returns:
            Dict[str, Any]: 统计数据，字段名与前端API期望一致
        """
        try:
            # 1. 统计不同学习类型数量 (unique_styles)
            unique_types_stmt = select(func.count(func.distinct(StyleLearningReview.type)))
            unique_types_result = await self.session.execute(unique_types_stmt)
            unique_styles = unique_types_result.scalar() or 0

            # 2. 计算平均置信度 (avg_confidence) - 暂时返回批准率
            total_stmt = select(func.count()).select_from(StyleLearningReview)
            total_result = await self.session.execute(total_stmt)
            total_patterns = total_result.scalar() or 0

            approved_stmt = select(func.count()).select_from(StyleLearningReview).where(
                StyleLearningReview.status == 'approved'
            )
            approved_result = await self.session.execute(approved_stmt)
            approved_patterns = approved_result.scalar() or 0

            # 平均置信度 = 批准率
            avg_confidence = round((approved_patterns / total_patterns * 100), 1) if total_patterns > 0 else 0.0

            # 3. 获取原始消息总数 (total_samples)
            # 从 style_learning_reviews 表获取累计的消息数量
            # 注意：这个字段可能不存在，需要根据实际情况调整
            total_samples = total_patterns  # 暂时用总模式数代替

            # 4. 最后更新时间 (latest_update)
            # 使用 timestamp 而不是 updated_at，因为 timestamp 是数值类型
            last_update_stmt = select(func.max(StyleLearningReview.timestamp))
            last_update_result = await self.session.execute(last_update_stmt)
            latest_update = last_update_result.scalar()

            return {
                "unique_styles": unique_styles,
                "avg_confidence": avg_confidence,
                "total_samples": total_samples,
                "latest_update": latest_update
            }

        except Exception as e:
            logger.error(f"[StyleLearningReviewRepository] 获取统计数据失败: {e}")
            return {
                "unique_styles": 0,
                "avg_confidence": 0.0,
                "total_samples": 0,
                "latest_update": None
            }


class StyleLearningPatternRepository(BaseRepository[StyleLearningPattern]):
    """风格学习模式 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, StyleLearningPattern)

    async def get_patterns_by_type(
        self,
        group_id: str,
        pattern_type: str,
        limit: int = 100
    ) -> List[StyleLearningPattern]:
        """
        根据类型获取模式

        Args:
            group_id: 群组 ID
            pattern_type: 模式类型
            limit: 最大返回数量

        Returns:
            List[StyleLearningPattern]: 模式列表
        """
        try:
            stmt = select(StyleLearningPattern).where(
                and_(
                    StyleLearningPattern.group_id == group_id,
                    StyleLearningPattern.pattern_type == pattern_type
                )
            ).order_by(
                desc(StyleLearningPattern.usage_count)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[StyleLearningPatternRepository] 获取模式失败: {e}")
            return []

    async def increment_usage(self, pattern_id: int) -> bool:
        """
        增加模式使用次数

        Args:
            pattern_id: 模式 ID

        Returns:
            bool: 是否成功
        """
        try:
            current_time = int(time.time())
            pattern = await self.get_by_id(pattern_id)
            if not pattern:
                return False

            pattern.usage_count += 1
            pattern.last_used = current_time
            pattern.updated_at = current_time

            return await self.update(pattern) is not None

        except Exception as e:
            logger.error(f"[StyleLearningPatternRepository] 增加使用次数失败: {e}")
            return False


class InteractionRecordRepository(BaseRepository[InteractionRecord]):
    """互动记录 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, InteractionRecord)

    async def get_interaction_trend(
        self,
        days: int = 7,
        group_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取互动趋势（按天统计）

        Args:
            days: 天数
            group_id: 群组 ID（可选）

        Returns:
            List[Dict]: 趋势数据
        """
        try:
            from datetime import datetime, timedelta

            # 计算起始时间
            start_time = int((datetime.now() - timedelta(days=days)).timestamp())

            # 构建查询
            stmt = select(
                func.date(func.from_unixtime(InteractionRecord.timestamp)).label('date'),
                func.count(InteractionRecord.id).label('count')
            ).where(
                InteractionRecord.timestamp >= start_time
            )

            if group_id:
                stmt = stmt.where(InteractionRecord.group_id == group_id)

            stmt = stmt.group_by(
                func.date(func.from_unixtime(InteractionRecord.timestamp))
            ).order_by('date')

            result = await self.session.execute(stmt)
            return [
                {
                    'date': str(row.date),
                    'count': row.count
                }
                for row in result
            ]

        except Exception as e:
            logger.error(f"[InteractionRecordRepository] 获取互动趋势失败: {e}")
            return []

    async def record_interaction(
        self,
        group_id: str,
        user_id: str,
        interaction_type: str,
        content_preview: Optional[str] = None
    ) -> Optional[InteractionRecord]:
        """
        记录互动

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            interaction_type: 互动类型
            content_preview: 内容预览

        Returns:
            Optional[InteractionRecord]: 创建的记录
        """
        try:
            current_time = int(time.time())
            return await self.create(
                group_id=group_id,
                user_id=user_id,
                interaction_type=interaction_type,
                content_preview=content_preview[:200] if content_preview else None,
                timestamp=current_time
            )
        except Exception as e:
            logger.error(f"[InteractionRecordRepository] 记录互动失败: {e}")
            return None
