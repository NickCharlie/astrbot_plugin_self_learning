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
    InteractionRecord,
    LearningBatch,
    LearningSession,
    LearningReinforcementFeedback,
    LearningOptimizationLog
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
            from datetime import datetime

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
            total_samples = total_patterns # 暂时用总模式数代替

            # 4. 最后更新时间 (latest_update)
            # 使用 timestamp 而不是 updated_at，因为 timestamp 是数值类型
            last_update_stmt = select(func.max(StyleLearningReview.timestamp))
            last_update_result = await self.session.execute(last_update_stmt)
            latest_timestamp = last_update_result.scalar()

            # 转换 Unix 时间戳为可读格式
            latest_update = None
            if latest_timestamp:
                latest_update = datetime.fromtimestamp(latest_timestamp).strftime('%Y-%m-%d %H:%M:%S')

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


class LearningBatchRepository(BaseRepository[LearningBatch]):
    """学习批次 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LearningBatch)

    async def save_learning_batch(
        self,
        batch_id: str,
        batch_name: str,
        group_id: str,
        start_time: float,
        end_time: Optional[float] = None,
        quality_score: Optional[float] = None,
        processed_messages: int = 0,
        message_count: int = 0,
        filtered_count: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        status: str = 'pending'
    ) -> Optional[LearningBatch]:
        """
        保存学习批次

        Args:
            batch_id: 批次 ID
            batch_name: 批次名称
            group_id: 群组 ID
            start_time: 开始时间
            end_time: 结束时间
            quality_score: 质量分数
            processed_messages: 已处理消息数
            message_count: 总消息数
            filtered_count: 过滤掉的消息数
            success: 是否成功
            error_message: 错误信息
            status: 状态

        Returns:
            Optional[LearningBatch]: 创建的批次记录
        """
        try:
            return await self.create(
                batch_id=batch_id,
                batch_name=batch_name,
                group_id=group_id,
                start_time=start_time,
                end_time=end_time,
                quality_score=quality_score,
                processed_messages=processed_messages,
                message_count=message_count,
                filtered_count=filtered_count,
                success=success,
                error_message=error_message,
                status=status
            )
        except Exception as e:
            logger.error(f"[LearningBatchRepository] 保存学习批次失败: {e}")
            return None

    async def get_learning_batches(
        self,
        group_id: str,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[LearningBatch]:
        """
        获取学习批次列表

        Args:
            group_id: 群组 ID
            limit: 最大返回数量
            offset: 偏移量
            status_filter: 状态过滤

        Returns:
            List[LearningBatch]: 批次列表
        """
        try:
            stmt = select(LearningBatch).where(
                LearningBatch.group_id == group_id
            )

            if status_filter:
                stmt = stmt.where(LearningBatch.status == status_filter)

            stmt = stmt.order_by(
                desc(LearningBatch.start_time)
            ).offset(offset).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[LearningBatchRepository] 获取学习批次列表失败: {e}")
            return []

    async def get_learning_batch_by_id(self, batch_id: str) -> Optional[LearningBatch]:
        """
        根据 batch_id 获取学习批次

        Args:
            batch_id: 批次 ID

        Returns:
            Optional[LearningBatch]: 批次记录
        """
        try:
            stmt = select(LearningBatch).where(
                LearningBatch.batch_id == batch_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[LearningBatchRepository] 根据batch_id获取学习批次失败: {e}")
            return None

    async def update_batch_status(
        self,
        batch_id: str,
        status: str,
        end_time: Optional[float] = None,
        quality_score: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        更新批次状态

        Args:
            batch_id: 批次 ID
            status: 新状态
            end_time: 结束时间
            quality_score: 质量分数
            error_message: 错误信息

        Returns:
            bool: 是否成功
        """
        try:
            batch = await self.get_learning_batch_by_id(batch_id)
            if not batch:
                return False

            batch.status = status
            if end_time is not None:
                batch.end_time = end_time
            if quality_score is not None:
                batch.quality_score = quality_score
            if error_message is not None:
                batch.error_message = error_message

            return await self.update(batch) is not None

        except Exception as e:
            logger.error(f"[LearningBatchRepository] 更新批次状态失败: {e}")
            return False

    async def get_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取学习批次统计

        Args:
            group_id: 群组 ID

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总批次数
            total_stmt = select(func.count()).select_from(LearningBatch).where(
                LearningBatch.group_id == group_id
            )
            total_result = await self.session.execute(total_stmt)
            total_count = total_result.scalar() or 0

            # 成功批次数
            success_stmt = select(func.count()).select_from(LearningBatch).where(
                and_(
                    LearningBatch.group_id == group_id,
                    LearningBatch.success == True
                )
            )
            success_result = await self.session.execute(success_stmt)
            success_count = success_result.scalar() or 0

            # 平均质量分数
            avg_quality_stmt = select(func.avg(LearningBatch.quality_score)).where(
                and_(
                    LearningBatch.group_id == group_id,
                    LearningBatch.quality_score.isnot(None)
                )
            )
            avg_quality_result = await self.session.execute(avg_quality_stmt)
            avg_quality = avg_quality_result.scalar() or 0.0

            # 总处理消息数
            total_messages_stmt = select(func.sum(LearningBatch.processed_messages)).where(
                LearningBatch.group_id == group_id
            )
            total_messages_result = await self.session.execute(total_messages_stmt)
            total_messages = total_messages_result.scalar() or 0

            return {
                "total_batches": total_count,
                "success_batches": success_count,
                "success_rate": round((success_count / total_count), 2) if total_count > 0 else 0.0,
                "avg_quality_score": round(float(avg_quality), 2),
                "total_processed_messages": total_messages
            }

        except Exception as e:
            logger.error(f"[LearningBatchRepository] 获取统计数据失败: {e}")
            return {
                "total_batches": 0,
                "success_batches": 0,
                "success_rate": 0.0,
                "avg_quality_score": 0.0,
                "total_processed_messages": 0
            }


class LearningSessionRepository(BaseRepository[LearningSession]):
    """学习会话 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LearningSession)

    async def save_learning_session(
        self,
        session_id: str,
        group_id: str,
        batch_id: Optional[str] = None,
        start_time: float = None,
        end_time: Optional[float] = None,
        metrics: Optional[str] = None
    ) -> Optional[LearningSession]:
        """
        保存学习会话

        Args:
            session_id: 会话 ID
            group_id: 群组 ID
            batch_id: 批次 ID
            start_time: 开始时间
            end_time: 结束时间
            metrics: 指标数据（JSON字符串）

        Returns:
            Optional[LearningSession]: 创建的会话记录
        """
        try:
            if start_time is None:
                start_time = time.time()

            return await self.create(
                session_id=session_id,
                group_id=group_id,
                batch_id=batch_id,
                start_time=start_time,
                end_time=end_time,
                metrics=metrics
            )
        except Exception as e:
            logger.error(f"[LearningSessionRepository] 保存学习会话失败: {e}")
            return None

    async def get_learning_sessions(
        self,
        group_id: str,
        batch_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[LearningSession]:
        """
        获取学习会话列表

        Args:
            group_id: 群组 ID
            batch_id: 批次 ID（可选）
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            List[LearningSession]: 会话列表
        """
        try:
            stmt = select(LearningSession).where(
                LearningSession.group_id == group_id
            )

            if batch_id:
                stmt = stmt.where(LearningSession.batch_id == batch_id)

            stmt = stmt.order_by(
                desc(LearningSession.start_time)
            ).offset(offset).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[LearningSessionRepository] 获取学习会话列表失败: {e}")
            return []

    async def get_session_by_id(self, session_id: str) -> Optional[LearningSession]:
        """
        根据 session_id 获取学习会话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[LearningSession]: 会话记录
        """
        try:
            stmt = select(LearningSession).where(
                LearningSession.session_id == session_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[LearningSessionRepository] 根据session_id获取学习会话失败: {e}")
            return None

    async def update_session_metrics(
        self,
        session_id: str,
        end_time: float,
        metrics: str
    ) -> bool:
        """
        更新会话指标

        Args:
            session_id: 会话 ID
            end_time: 结束时间
            metrics: 指标数据（JSON字符串）

        Returns:
            bool: 是否成功
        """
        try:
            learning_session = await self.get_session_by_id(session_id)
            if not learning_session:
                return False

            learning_session.end_time = end_time
            learning_session.metrics = metrics

            return await self.update(learning_session) is not None

        except Exception as e:
            logger.error(f"[LearningSessionRepository] 更新会话指标失败: {e}")
            return False


class LearningReinforcementFeedbackRepository(BaseRepository[LearningReinforcementFeedback]):
    """学习强化反馈 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LearningReinforcementFeedback)

    async def save_reinforcement_feedback(
        self,
        group_id: str,
        feedback_type: str,
        feedback_content: Optional[str] = None,
        effectiveness_score: Optional[float] = None,
        applied_at: Optional[float] = None
    ) -> Optional[LearningReinforcementFeedback]:
        """
        保存强化学习反馈

        Args:
            group_id: 群组 ID
            feedback_type: 反馈类型 (positive, negative, neutral)
            feedback_content: 反馈内容
            effectiveness_score: 有效性评分
            applied_at: 应用时间戳

        Returns:
            Optional[LearningReinforcementFeedback]: 创建的反馈记录
        """
        try:
            if applied_at is None:
                applied_at = time.time()

            return await self.create(
                group_id=group_id,
                feedback_type=feedback_type,
                feedback_content=feedback_content,
                effectiveness_score=effectiveness_score,
                applied_at=applied_at
            )
        except Exception as e:
            logger.error(f"[LearningReinforcementFeedbackRepository] 保存反馈失败: {e}")
            return None

    async def get_recent_feedbacks(
        self,
        group_id: str,
        feedback_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[LearningReinforcementFeedback]:
        """
        获取最近的强化反馈

        Args:
            group_id: 群组 ID
            feedback_type: 反馈类型过滤（可选）
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            List[LearningReinforcementFeedback]: 反馈列表
        """
        try:
            stmt = select(LearningReinforcementFeedback).where(
                LearningReinforcementFeedback.group_id == group_id
            )

            if feedback_type:
                stmt = stmt.where(LearningReinforcementFeedback.feedback_type == feedback_type)

            stmt = stmt.order_by(
                desc(LearningReinforcementFeedback.applied_at)
            ).offset(offset).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[LearningReinforcementFeedbackRepository] 获取反馈列表失败: {e}")
            return []

    async def get_effectiveness_statistics(
        self,
        group_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取反馈有效性统计

        Args:
            group_id: 群组 ID
            days: 统计天数

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            from datetime import datetime, timedelta

            cutoff_time = (datetime.now() - timedelta(days=days)).timestamp()

            # 统计各类型反馈数量
            stmt = select(
                LearningReinforcementFeedback.feedback_type,
                func.count(LearningReinforcementFeedback.id).label('count'),
                func.avg(LearningReinforcementFeedback.effectiveness_score).label('avg_score')
            ).where(
                and_(
                    LearningReinforcementFeedback.group_id == group_id,
                    LearningReinforcementFeedback.applied_at >= cutoff_time
                )
            ).group_by(LearningReinforcementFeedback.feedback_type)

            result = await self.session.execute(stmt)
            rows = result.fetchall()

            statistics = {
                'total_feedbacks': 0,
                'by_type': {},
                'avg_effectiveness': 0.0
            }

            total_score = 0.0
            total_count = 0

            for row in rows:
                feedback_type, count, avg_score = row
                statistics['by_type'][feedback_type] = {
                    'count': count,
                    'avg_effectiveness': round(float(avg_score) if avg_score else 0.0, 2)
                }
                statistics['total_feedbacks'] += count
                if avg_score:
                    total_score += avg_score * count
                    total_count += count

            if total_count > 0:
                statistics['avg_effectiveness'] = round(total_score / total_count, 2)

            return statistics

        except Exception as e:
            logger.error(f"[LearningReinforcementFeedbackRepository] 获取统计数据失败: {e}")
            return {
                'total_feedbacks': 0,
                'by_type': {},
                'avg_effectiveness': 0.0
            }


class LearningOptimizationLogRepository(BaseRepository[LearningOptimizationLog]):
    """学习优化日志 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LearningOptimizationLog)

    async def save_optimization_log(
        self,
        group_id: str,
        optimization_type: str,
        parameters: Optional[str] = None,
        before_metrics: Optional[str] = None,
        after_metrics: Optional[str] = None,
        improvement_rate: Optional[float] = None,
        applied_at: Optional[float] = None
    ) -> Optional[LearningOptimizationLog]:
        """
        保存优化日志

        Args:
            group_id: 群组 ID
            optimization_type: 优化类型
            parameters: 参数配置（JSON字符串）
            before_metrics: 优化前指标（JSON字符串）
            after_metrics: 优化后指标（JSON字符串）
            improvement_rate: 改进率
            applied_at: 应用时间戳

        Returns:
            Optional[LearningOptimizationLog]: 创建的日志记录
        """
        try:
            if applied_at is None:
                applied_at = time.time()

            return await self.create(
                group_id=group_id,
                optimization_type=optimization_type,
                parameters=parameters,
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                improvement_rate=improvement_rate,
                applied_at=applied_at
            )
        except Exception as e:
            logger.error(f"[LearningOptimizationLogRepository] 保存优化日志失败: {e}")
            return None

    async def get_optimization_logs(
        self,
        group_id: str,
        optimization_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[LearningOptimizationLog]:
        """
        获取优化日志列表

        Args:
            group_id: 群组 ID
            optimization_type: 优化类型过滤（可选）
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            List[LearningOptimizationLog]: 日志列表
        """
        try:
            stmt = select(LearningOptimizationLog).where(
                LearningOptimizationLog.group_id == group_id
            )

            if optimization_type:
                stmt = stmt.where(LearningOptimizationLog.optimization_type == optimization_type)

            stmt = stmt.order_by(
                desc(LearningOptimizationLog.applied_at)
            ).offset(offset).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[LearningOptimizationLogRepository] 获取优化日志列表失败: {e}")
            return []

    async def get_improvement_statistics(
        self,
        group_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取优化改进统计

        Args:
            group_id: 群组 ID
            days: 统计天数

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            from datetime import datetime, timedelta

            cutoff_time = (datetime.now() - timedelta(days=days)).timestamp()

            # 统计各优化类型的改进情况
            stmt = select(
                LearningOptimizationLog.optimization_type,
                func.count(LearningOptimizationLog.id).label('count'),
                func.avg(LearningOptimizationLog.improvement_rate).label('avg_improvement'),
                func.max(LearningOptimizationLog.improvement_rate).label('max_improvement')
            ).where(
                and_(
                    LearningOptimizationLog.group_id == group_id,
                    LearningOptimizationLog.applied_at >= cutoff_time,
                    LearningOptimizationLog.improvement_rate.isnot(None)
                )
            ).group_by(LearningOptimizationLog.optimization_type)

            result = await self.session.execute(stmt)
            rows = result.fetchall()

            statistics = {
                'total_optimizations': 0,
                'by_type': {},
                'overall_avg_improvement': 0.0
            }

            total_improvement = 0.0
            total_count = 0

            for row in rows:
                opt_type, count, avg_improvement, max_improvement = row
                statistics['by_type'][opt_type] = {
                    'count': count,
                    'avg_improvement': round(float(avg_improvement) if avg_improvement else 0.0, 2),
                    'max_improvement': round(float(max_improvement) if max_improvement else 0.0, 2)
                }
                statistics['total_optimizations'] += count
                if avg_improvement:
                    total_improvement += avg_improvement * count
                    total_count += count

            if total_count > 0:
                statistics['overall_avg_improvement'] = round(total_improvement / total_count, 2)

            return statistics

        except Exception as e:
            logger.error(f"[LearningOptimizationLogRepository] 获取统计数据失败: {e}")
            return {
                'total_optimizations': 0,
                'by_type': {},
                'overall_avg_improvement': 0.0
            }
