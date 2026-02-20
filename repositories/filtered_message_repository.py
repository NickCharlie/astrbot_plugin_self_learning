"""
筛选后消息 Repository — FilteredMessage 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func, delete
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.message import FilteredMessage


class FilteredMessageRepository(BaseRepository[FilteredMessage]):
    """筛选后消息 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FilteredMessage)

    async def add(self, message_data: Dict[str, Any]) -> Optional[FilteredMessage]:
        """
        添加一条筛选后的消息

        Args:
            message_data: 消息字段字典

        Returns:
            Optional[FilteredMessage]: 创建的记录
        """
        try:
            now = int(time.time())
            return await self.create(
                raw_message_id=message_data.get('raw_message_id'),
                message=message_data.get('message', ''),
                sender_id=message_data.get('sender_id', ''),
                group_id=message_data.get('group_id', ''),
                timestamp=message_data.get('timestamp', now),
                confidence=message_data.get('confidence'),
                quality_scores=message_data.get('quality_scores'),
                filter_reason=message_data.get('filter_reason'),
                created_at=now,
                processed=False,
            )
        except Exception as e:
            logger.error(f"[FilteredMessageRepository] 添加筛选消息失败: {e}")
            return None

    async def get_for_learning(self, limit: int = 200) -> List[FilteredMessage]:
        """
        获取待学习的筛选消息（未处理的）

        Args:
            limit: 最大返回数量

        Returns:
            List[FilteredMessage]: 待学习消息列表（按时间升序）
        """
        try:
            stmt = (
                select(FilteredMessage)
                .where(FilteredMessage.processed == False)  # noqa: E712
                .order_by(FilteredMessage.timestamp.asc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[FilteredMessageRepository] 获取待学习消息失败: {e}")
            return []

    async def mark_processed(self, message_id: int) -> bool:
        """
        标记为已处理

        Args:
            message_id: 消息 ID

        Returns:
            bool: 是否成功
        """
        try:
            stmt = (
                update(FilteredMessage)
                .where(FilteredMessage.id == message_id)
                .values(processed=True)
            )
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[FilteredMessageRepository] 标记已处理失败: {e}")
            return False

    async def mark_batch_processed(self, message_ids: List[int]) -> int:
        """
        批量标记为已处理

        Args:
            message_ids: 消息 ID 列表

        Returns:
            int: 成功标记的数量
        """
        if not message_ids:
            return 0
        try:
            stmt = (
                update(FilteredMessage)
                .where(FilteredMessage.id.in_(message_ids))
                .values(processed=True)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[FilteredMessageRepository] 批量标记已处理失败: {e}")
            return 0

    async def get_recent(
        self,
        group_id: Optional[str] = None,
        limit: int = 50
    ) -> List[FilteredMessage]:
        """
        获取最近的筛选消息

        Args:
            group_id: 群组 ID（为 None 时不过滤）
            limit: 最大返回数量

        Returns:
            List[FilteredMessage]: 消息列表（按时间倒序）
        """
        try:
            stmt = select(FilteredMessage)
            if group_id:
                stmt = stmt.where(FilteredMessage.group_id == group_id)
            stmt = stmt.order_by(desc(FilteredMessage.timestamp)).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[FilteredMessageRepository] 获取最近筛选消息失败: {e}")
            return []

    async def count_all(self, group_id: Optional[str] = None) -> int:
        """
        统计消息总数

        Args:
            group_id: 群组 ID（为 None 时统计全部）

        Returns:
            int: 消息数量
        """
        try:
            stmt = select(func.count()).select_from(FilteredMessage)
            if group_id:
                stmt = stmt.where(FilteredMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[FilteredMessageRepository] 统计消息失败: {e}")
            return 0

    async def delete_by_group(self, group_id: str) -> int:
        """
        删除指定群组的所有筛选消息

        Args:
            group_id: 群组 ID

        Returns:
            int: 删除的行数
        """
        try:
            stmt = delete(FilteredMessage).where(FilteredMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[FilteredMessageRepository] 删除群组筛选消息失败: {e}")
            return 0

    async def get_by_confidence_range(
        self,
        group_id: str,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0,
        limit: int = 100
    ) -> List[FilteredMessage]:
        """
        按置信度范围获取消息

        Args:
            group_id: 群组 ID
            min_confidence: 最小置信度
            max_confidence: 最大置信度
            limit: 最大返回数量

        Returns:
            List[FilteredMessage]: 消息列表
        """
        try:
            stmt = (
                select(FilteredMessage)
                .where(and_(
                    FilteredMessage.group_id == group_id,
                    FilteredMessage.confidence >= min_confidence,
                    FilteredMessage.confidence <= max_confidence,
                ))
                .order_by(desc(FilteredMessage.confidence))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[FilteredMessageRepository] 按置信度获取消息失败: {e}")
            return []
