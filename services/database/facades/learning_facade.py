"""
学习 Facade — 人格学习审核、风格学习审核、学习批次/会话、统计的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade


class LearningFacade(BaseFacade):
    """学习管理 Facade — 包装所有学习相关的数据库方法"""

    # Persona Learning Review methods

    async def add_persona_learning_review(self, review_data: Dict[str, Any]) -> int:
        """创建人格学习审核记录

        Args:
            review_data: 审核数据字典

        Returns:
            新记录的 id，失败返回 0
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.learning import PersonaLearningReview

                metadata = review_data.get('metadata', {})
                record = PersonaLearningReview(
                    timestamp=review_data.get('timestamp', time.time()),
                    group_id=review_data.get('group_id', ''),
                    update_type=review_data.get('update_type', ''),
                    original_content=review_data.get('original_content', ''),
                    new_content=review_data.get('new_content', ''),
                    proposed_content=review_data.get('proposed_content', ''),
                    confidence_score=review_data.get('confidence_score', 0.0),
                    reason=review_data.get('reason', ''),
                    status='pending',
                    metadata_=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return record.id
        except Exception as e:
            self._logger.error(f"[LearningFacade] 添加人格学习审核记录失败: {e}")
            return 0

    async def get_pending_persona_update_records(self) -> List[Dict[str, Any]]:
        """获取所有待审核的人格更新记录

        Returns:
            待审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import PersonaLearningReview

                stmt = (
                    select(PersonaLearningReview)
                    .where(PersonaLearningReview.status == 'pending')
                    .order_by(desc(PersonaLearningReview.timestamp))
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'original_content': r.original_content,
                        'new_content': r.new_content,
                        'proposed_content': r.proposed_content,
                        'confidence_score': r.confidence_score,
                        'reason': r.reason,
                        'status': r.status,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                        'metadata': json.loads(r.metadata_) if r.metadata_ else {},
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取待审核人格更新记录失败: {e}")
            return []

    async def save_persona_update_record(self, record: Dict[str, Any]) -> int:
        """保存人格更新记录（add_persona_learning_review 的别名）

        Args:
            record: 记录数据字典

        Returns:
            新记录的 id，失败返回 0
        """
        return await self.add_persona_learning_review(record)

    async def update_persona_update_record_status(
        self, record_id: int, new_status: str, reviewer_comment: str = ''
    ) -> bool:
        """更新人格更新记录的状态

        Args:
            record_id: 记录 ID
            new_status: 新状态 (approved/rejected)
            reviewer_comment: 审核评论

        Returns:
            是否更新成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                record.status = new_status
                record.reviewer_comment = reviewer_comment
                record.review_time = time.time()
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 更新人格更新记录状态失败: {e}")
            return False

    async def delete_persona_update_record(self, record_id: int) -> bool:
        """删除人格更新记录

        Args:
            record_id: 记录 ID

        Returns:
            是否删除成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, delete as sa_delete
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                await session.execute(
                    sa_delete(PersonaLearningReview).where(
                        PersonaLearningReview.id == record_id
                    )
                )
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 删除人格更新记录失败: {e}")
            return False

    async def get_persona_update_record_by_id(
        self, record_id: int
    ) -> Optional[Dict[str, Any]]:
        """根据 ID 获取人格更新记录

        Args:
            record_id: 记录 ID

        Returns:
            记录字典或 None
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                r = result.scalar_one_or_none()
                if not r:
                    return None
                return {
                    'id': r.id,
                    'timestamp': r.timestamp,
                    'group_id': r.group_id,
                    'update_type': r.update_type,
                    'original_content': r.original_content,
                    'new_content': r.new_content,
                    'proposed_content': r.proposed_content,
                    'confidence_score': r.confidence_score,
                    'reason': r.reason,
                    'status': r.status,
                    'reviewer_comment': r.reviewer_comment,
                    'review_time': r.review_time,
                    'metadata': json.loads(r.metadata_) if r.metadata_ else {},
                }
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取人格更新记录失败: {e}")
            return None

    async def get_reviewed_persona_update_records(
        self, limit: int = 50, offset: int = 0, status_filter: str = None
    ) -> List[Dict[str, Any]]:
        """获取已审核的人格更新记录

        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 状态过滤

        Returns:
            已审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import PersonaLearningReview

                if status_filter:
                    stmt = (
                        select(PersonaLearningReview)
                        .where(PersonaLearningReview.status == status_filter)
                        .order_by(desc(PersonaLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )
                else:
                    stmt = (
                        select(PersonaLearningReview)
                        .where(PersonaLearningReview.status.in_(['approved', 'rejected']))
                        .order_by(desc(PersonaLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'original_content': r.original_content,
                        'new_content': r.new_content,
                        'proposed_content': r.proposed_content,
                        'confidence_score': r.confidence_score,
                        'reason': r.reason,
                        'status': r.status,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                        'metadata': json.loads(r.metadata_) if r.metadata_ else {},
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取已审核人格更新记录失败: {e}")
            return []

    async def get_pending_persona_learning_reviews(
        self, limit: int = None
    ) -> List[Dict[str, Any]]:
        """获取待审核的人格学习审核记录（支持 limit 参数）

        Args:
            limit: 可选的返回数量限制

        Returns:
            待审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import PersonaLearningReview

                stmt = (
                    select(PersonaLearningReview)
                    .where(PersonaLearningReview.status == 'pending')
                    .order_by(desc(PersonaLearningReview.timestamp))
                )
                if limit is not None:
                    stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'original_content': r.original_content,
                        'new_content': r.new_content,
                        'proposed_content': r.proposed_content,
                        'confidence_score': r.confidence_score,
                        'reason': r.reason,
                        'status': r.status,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                        'metadata': json.loads(r.metadata_) if r.metadata_ else {},
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取待审核人格学习审核记录失败: {e}")
            return []

    async def get_reviewed_persona_learning_updates(
        self, limit=50, offset=0, status_filter=None
    ) -> List[Dict]:
        """获取已审核的人格学习更新记录

        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 状态过滤

        Returns:
            已审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import PersonaLearningReview

                if status_filter:
                    stmt = (
                        select(PersonaLearningReview)
                        .where(PersonaLearningReview.status == status_filter)
                        .order_by(desc(PersonaLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )
                else:
                    stmt = (
                        select(PersonaLearningReview)
                        .where(PersonaLearningReview.status.in_(['approved', 'rejected']))
                        .order_by(desc(PersonaLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'original_content': r.original_content,
                        'new_content': r.new_content,
                        'proposed_content': r.proposed_content,
                        'confidence_score': r.confidence_score,
                        'reason': r.reason,
                        'status': r.status,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取已审核人格学习更新记录失败: {e}")
            return []

    async def delete_persona_learning_review_by_id(self, review_id: int) -> bool:
        """根据 ID 删除人格学习审核记录

        Args:
            review_id: 审核记录 ID

        Returns:
            是否删除成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, delete as sa_delete
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == review_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                await session.execute(
                    sa_delete(PersonaLearningReview).where(
                        PersonaLearningReview.id == review_id
                    )
                )
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 删除人格学习审核记录失败: {e}")
            return False

    async def get_persona_learning_review_by_id(
        self, review_id: int
    ) -> Optional[Dict]:
        """根据 ID 获取人格学习审核记录（get_persona_update_record_by_id 的别名）

        Args:
            review_id: 审核记录 ID

        Returns:
            记录字典或 None
        """
        return await self.get_persona_update_record_by_id(review_id)

    async def update_persona_learning_review_status(
        self, review_id, new_status, reviewer_comment='',
        modified_content=None,
    ) -> bool:
        """更新人格学习审核记录状态

        Args:
            review_id: 审核记录 ID
            new_status: 新状态
            reviewer_comment: 审核评论
            modified_content: 用户修改后的内容（可选）

        Returns:
            是否更新成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == review_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                record.status = new_status
                record.reviewer_comment = reviewer_comment
                record.review_time = time.time()

                if modified_content:
                    record.proposed_content = modified_content
                    record.new_content = modified_content

                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 更新人格学习审核记录状态失败: {e}")
            return False

    # Style Learning Review methods

    async def create_style_learning_review(
        self, review_data: Dict[str, Any]
    ) -> int:
        """创建风格学习审核记录

        Args:
            review_data: 审核数据字典

        Returns:
            新记录的 id，失败返回 0
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.learning import StyleLearningReview

                learned_patterns = review_data.get('learned_patterns', [])
                record = StyleLearningReview(
                    type=review_data.get('type', ''),
                    group_id=review_data.get('group_id', ''),
                    timestamp=review_data.get('timestamp', time.time()),
                    learned_patterns=json.dumps(learned_patterns, ensure_ascii=False)
                    if isinstance(learned_patterns, (list, dict))
                    else learned_patterns,
                    few_shots_content=review_data.get('few_shots_content', ''),
                    status='pending',
                    description=review_data.get('description', ''),
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return record.id
        except Exception as e:
            self._logger.error(f"[LearningFacade] 创建风格学习审核记录失败: {e}")
            return 0

    async def get_pending_style_reviews(self, limit=None) -> List[Dict]:
        """获取待审核的风格学习记录

        Args:
            limit: 可选的返回数量限制

        Returns:
            待审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import StyleLearningReview

                stmt = (
                    select(StyleLearningReview)
                    .where(StyleLearningReview.status == 'pending')
                    .order_by(desc(StyleLearningReview.timestamp))
                )
                if limit is not None:
                    stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'type': r.type,
                        'group_id': r.group_id,
                        'timestamp': r.timestamp,
                        'learned_patterns': json.loads(r.learned_patterns)
                        if r.learned_patterns
                        else [],
                        'few_shots_content': r.few_shots_content,
                        'status': r.status,
                        'description': r.description,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                        'created_at': r.created_at,
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取待审核风格学习记录失败: {e}")
            return []

    async def get_reviewed_style_learning_updates(
        self, limit=50, offset=0, status_filter=None
    ) -> List[Dict]:
        """获取已审核的风格学习更新记录

        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 状态过滤

        Returns:
            已审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import StyleLearningReview

                if status_filter:
                    stmt = (
                        select(StyleLearningReview)
                        .where(StyleLearningReview.status == status_filter)
                        .order_by(desc(StyleLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )
                else:
                    stmt = (
                        select(StyleLearningReview)
                        .where(StyleLearningReview.status.in_(['approved', 'rejected']))
                        .order_by(desc(StyleLearningReview.review_time))
                        .offset(offset)
                        .limit(limit)
                    )

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'type': r.type,
                        'group_id': r.group_id,
                        'timestamp': r.timestamp,
                        'learned_patterns': json.loads(r.learned_patterns)
                        if r.learned_patterns
                        else [],
                        'few_shots_content': r.few_shots_content,
                        'status': r.status,
                        'description': r.description,
                        'reviewer_comment': r.reviewer_comment,
                        'review_time': r.review_time,
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取已审核风格学习更新记录失败: {e}")
            return []

    async def update_style_review_status(
        self, review_id, new_status, reviewer_comment=''
    ) -> bool:
        """更新风格学习审核记录状态

        Args:
            review_id: 审核记录 ID
            new_status: 新状态 (approved/rejected)
            reviewer_comment: 审核评论

        Returns:
            是否更新成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.learning import StyleLearningReview

                stmt = select(StyleLearningReview).where(
                    StyleLearningReview.id == review_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                record.status = new_status
                record.reviewer_comment = reviewer_comment
                record.review_time = time.time()
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 更新风格学习审核记录状态失败: {e}")
            return False

    async def delete_style_review_by_id(self, review_id: int) -> bool:
        """根据 ID 删除风格学习审核记录

        Args:
            review_id: 审核记录 ID

        Returns:
            是否删除成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, delete as sa_delete
                from ....models.orm.learning import StyleLearningReview

                stmt = select(StyleLearningReview).where(
                    StyleLearningReview.id == review_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if not record:
                    return False

                await session.execute(
                    sa_delete(StyleLearningReview).where(
                        StyleLearningReview.id == review_id
                    )
                )
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 删除风格学习审核记录失败: {e}")
            return False

    # Learning Batch/Session methods

    async def get_learning_batch_history(
        self, group_id=None, limit=20
    ) -> List[Dict]:
        """获取学习批次历史

        Args:
            group_id: 可选的群组 ID 过滤
            limit: 返回数量限制

        Returns:
            学习批次记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import LearningBatch

                stmt = (
                    select(LearningBatch)
                    .order_by(desc(LearningBatch.start_time))
                    .limit(limit)
                )
                if group_id:
                    stmt = stmt.where(LearningBatch.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取学习批次历史失败: {e}")
            return []

    async def get_recent_learning_batches(self, limit=5) -> List[Dict]:
        """获取最近的学习批次

        Args:
            limit: 返回数量限制

        Returns:
            学习批次记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import LearningBatch

                stmt = (
                    select(LearningBatch)
                    .order_by(desc(LearningBatch.start_time))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取最近学习批次失败: {e}")
            return []

    async def get_learning_sessions(self, group_id, limit=5) -> List[Dict]:
        """获取指定群组的学习会话

        Args:
            group_id: 群组 ID
            limit: 返回数量限制

        Returns:
            学习会话记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import LearningSession

                stmt = (
                    select(LearningSession)
                    .where(LearningSession.group_id == group_id)
                    .order_by(desc(LearningSession.start_time))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取学习会话失败: {e}")
            return []

    async def get_recent_learning_sessions(self, days=7) -> List[Dict]:
        """获取最近 N 天的学习会话

        Args:
            days: 天数

        Returns:
            学习会话记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import LearningSession

                cutoff = time.time() - (days * 24 * 3600)
                stmt = (
                    select(LearningSession)
                    .where(LearningSession.start_time > cutoff)
                    .order_by(desc(LearningSession.start_time))
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取最近学习会话失败: {e}")
            return []

    async def save_learning_session_record(
        self, group_id, session_data
    ) -> bool:
        """保存学习会话记录

        Args:
            group_id: 群组 ID
            session_data: 会话数据字典

        Returns:
            是否保存成功
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.learning import LearningSession

                record = LearningSession(
                    session_id=session_data.get('session_id', ''),
                    group_id=group_id,
                    batch_id=session_data.get('batch_id'),
                    start_time=session_data.get('start_time', time.time()),
                    end_time=session_data.get('end_time'),
                    message_count=session_data.get('message_count', 0),
                    learning_quality=session_data.get('learning_quality'),
                    status=session_data.get('status', 'active'),
                )
                session.add(record)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 保存学习会话记录失败: {e}")
            return False

    async def save_learning_performance_record(
        self, group_id, performance_data
    ) -> bool:
        """保存学习性能记录

        Args:
            group_id: 群组 ID
            performance_data: 性能数据字典

        Returns:
            是否保存成功
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.performance import LearningPerformanceHistory

                metadata = performance_data.get('metadata', {})
                record = LearningPerformanceHistory(
                    group_id=group_id,
                    session_id=performance_data.get('session_id', ''),
                    timestamp=performance_data.get('timestamp', int(time.time())),
                    quality_score=performance_data.get('quality_score'),
                    learning_time=performance_data.get('learning_time'),
                    success=performance_data.get('success', True),
                    successful_pattern=json.dumps(
                        performance_data.get('successful_pattern', []),
                        ensure_ascii=False,
                    )
                    if isinstance(performance_data.get('successful_pattern'), (list, dict))
                    else performance_data.get('successful_pattern'),
                    failed_pattern=json.dumps(
                        performance_data.get('failed_pattern', []),
                        ensure_ascii=False,
                    )
                    if isinstance(performance_data.get('failed_pattern'), (list, dict))
                    else performance_data.get('failed_pattern'),
                    created_at=int(time.time()),
                )
                session.add(record)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[LearningFacade] 保存学习性能记录失败: {e}")
            return False

    # Statistics methods

    async def count_pending_persona_updates(self) -> int:
        """统计待审核的人格更新记录数

        Returns:
            待审核记录数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.learning import PersonaLearningReview

                stmt = (
                    select(func.count())
                    .select_from(PersonaLearningReview)
                    .where(PersonaLearningReview.status == 'pending')
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            self._logger.error(f"[LearningFacade] 统计待审核人格更新数量失败: {e}")
            return 0

    async def count_style_learning_patterns(self) -> int:
        """统计风格学习模式总数

        Returns:
            风格学习模式数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.learning import StyleLearningPattern

                stmt = select(func.count()).select_from(StyleLearningPattern)
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            self._logger.error(f"[LearningFacade] 统计风格学习模式数量失败: {e}")
            return 0

    async def count_refined_messages(self) -> int:
        """统计筛选后消息总数

        Returns:
            筛选后消息数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.message import FilteredMessage

                stmt = select(func.count()).select_from(FilteredMessage)
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            self._logger.error(f"[LearningFacade] 统计筛选后消息数量失败: {e}")
            return 0

    async def get_style_learning_statistics(self) -> Dict[str, Any]:
        """获取风格学习统计信息

        Returns:
            包含 total_reviews, pending_reviews, approved_reviews 的字典
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.learning import StyleLearningReview

                total_stmt = select(func.count()).select_from(StyleLearningReview)
                total_result = await session.execute(total_stmt)
                total = total_result.scalar() or 0

                pending_stmt = (
                    select(func.count())
                    .select_from(StyleLearningReview)
                    .where(StyleLearningReview.status == 'pending')
                )
                pending_result = await session.execute(pending_stmt)
                pending = pending_result.scalar() or 0

                approved_stmt = (
                    select(func.count())
                    .select_from(StyleLearningReview)
                    .where(StyleLearningReview.status == 'approved')
                )
                approved_result = await session.execute(approved_stmt)
                approved = approved_result.scalar() or 0

                return {
                    'total_reviews': total,
                    'pending_reviews': pending,
                    'approved_reviews': approved,
                }
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取风格学习统计失败: {e}")
            return {
                'total_reviews': 0,
                'pending_reviews': 0,
                'approved_reviews': 0,
            }

    async def get_style_progress_data(
        self, group_id=None
    ) -> List[Dict]:
        """获取风格学习进度数据（从 learning_batches 表查询）

        Args:
            group_id: 可选的群组 ID 过滤

        Returns:
            学习批次进度列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import LearningBatch

                stmt = (
                    select(LearningBatch)
                    .where(
                        LearningBatch.quality_score.isnot(None),
                        LearningBatch.processed_messages > 0,
                    )
                    .order_by(desc(LearningBatch.start_time))
                    .limit(30)
                )
                if group_id:
                    stmt = stmt.where(LearningBatch.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'group_id': r.group_id,
                        'timestamp': r.start_time or 0,
                        'quality_score': r.quality_score or 0,
                        'success': bool(r.success),
                        'processed_messages': r.processed_messages or 0,
                        'filtered_count': r.filtered_count or 0,
                        'message_count': r.message_count or 0,
                        'batch_name': r.batch_name or '',
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取风格学习进度数据失败: {e}")
            return []

    async def get_learning_patterns_data(
        self, group_id=None
    ) -> Dict[str, Any]:
        """获取学习模式分布数据

        按 pattern_type 分组统计 StyleLearningPattern 记录。

        Args:
            group_id: 可选的群组 ID 过滤

        Returns:
            按模式类型分组的计数字典
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.learning import StyleLearningPattern

                stmt = select(
                    StyleLearningPattern.pattern_type,
                    func.count().label('count'),
                ).group_by(StyleLearningPattern.pattern_type)
                if group_id:
                    stmt = stmt.where(StyleLearningPattern.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.all()
                pattern_counts = {row[0]: row[1] for row in rows}
                return pattern_counts
        except Exception as e:
            self._logger.error(f"[LearningFacade] 获取学习模式分布数据失败: {e}")
            return {}
