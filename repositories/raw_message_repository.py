"""
原始消息 Repository — RawMessage 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func, delete
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.message import RawMessage


class RawMessageRepository(BaseRepository[RawMessage]):
    """原始消息 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RawMessage)

    async def save(self, message_data: Dict[str, Any]) -> Optional[RawMessage]:
        """
        保存一条原始消息

        Args:
            message_data: 消息字段字典，至少包含 sender_id, message, timestamp

        Returns:
            Optional[RawMessage]: 创建的记录
        """
        try:
            now = int(time.time())
            return await self.create(
                sender_id=message_data.get('sender_id', ''),
                sender_name=message_data.get('sender_name', ''),
                message=message_data.get('message', ''),
                group_id=message_data.get('group_id', ''),
                timestamp=message_data.get('timestamp', now),
                platform=message_data.get('platform', ''),
                message_id=message_data.get('message_id'),
                reply_to=message_data.get('reply_to'),
                created_at=now,
                processed=False,
            )
        except Exception as e:
            logger.error(f"[RawMessageRepository] 保存原始消息失败: {e}")
            return None

    async def get_unprocessed(self, limit: int = 100) -> List[RawMessage]:
        """
        获取未处理的消息

        Args:
            limit: 最大返回数量

        Returns:
            List[RawMessage]: 未处理消息列表（按时间升序）
        """
        try:
            stmt = (
                select(RawMessage)
                .where(RawMessage.processed == False)  # noqa: E712
                .order_by(RawMessage.timestamp.asc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[RawMessageRepository] 获取未处理消息失败: {e}")
            return []

    async def mark_processed(self, message_id: int) -> bool:
        """
        将消息标记为已处理

        Args:
            message_id: 消息 ID

        Returns:
            bool: 是否成功
        """
        try:
            stmt = (
                update(RawMessage)
                .where(RawMessage.id == message_id)
                .values(processed=True)
            )
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[RawMessageRepository] 标记消息已处理失败: {e}")
            return False

    async def mark_batch_processed(self, message_ids: List[int]) -> int:
        """
        批量标记消息为已处理

        Args:
            message_ids: 消息 ID 列表

        Returns:
            int: 成功标记的数量
        """
        if not message_ids:
            return 0
        try:
            stmt = (
                update(RawMessage)
                .where(RawMessage.id.in_(message_ids))
                .values(processed=True)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[RawMessageRepository] 批量标记已处理失败: {e}")
            return 0

    async def get_recent(
        self,
        group_id: Optional[str] = None,
        limit: int = 50
    ) -> List[RawMessage]:
        """
        获取最近的消息

        Args:
            group_id: 群组 ID（为 None 时不过滤）
            limit: 最大返回数量

        Returns:
            List[RawMessage]: 消息列表（按时间倒序）
        """
        try:
            stmt = select(RawMessage)
            if group_id:
                stmt = stmt.where(RawMessage.group_id == group_id)
            stmt = stmt.order_by(desc(RawMessage.timestamp)).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[RawMessageRepository] 获取最近消息失败: {e}")
            return []

    async def get_by_timerange(
        self,
        group_id: str,
        start_ts: int,
        end_ts: int,
        limit: int = 500
    ) -> List[RawMessage]:
        """
        按时间范围获取消息

        Args:
            group_id: 群组 ID
            start_ts: 开始时间戳
            end_ts: 结束时间戳
            limit: 最大返回数量

        Returns:
            List[RawMessage]: 消息列表
        """
        try:
            stmt = (
                select(RawMessage)
                .where(and_(
                    RawMessage.group_id == group_id,
                    RawMessage.timestamp >= start_ts,
                    RawMessage.timestamp <= end_ts,
                ))
                .order_by(RawMessage.timestamp.asc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[RawMessageRepository] 按时间范围获取消息失败: {e}")
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
            stmt = select(func.count()).select_from(RawMessage)
            if group_id:
                stmt = stmt.where(RawMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[RawMessageRepository] 统计消息失败: {e}")
            return 0

    async def delete_by_group(self, group_id: str) -> int:
        """
        删除指定群组的所有消息

        Args:
            group_id: 群组 ID

        Returns:
            int: 删除的行数
        """
        try:
            stmt = delete(RawMessage).where(RawMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[RawMessageRepository] 删除群组消息失败: {e}")
            return 0

    async def get_sender_statistics(
        self,
        group_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取发送者统计信息

        Args:
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[Dict]: [{"sender_id": ..., "count": ...}, ...]
        """
        try:
            stmt = (
                select(
                    RawMessage.sender_id,
                    func.count().label('count')
                )
                .where(RawMessage.group_id == group_id)
                .group_by(RawMessage.sender_id)
                .order_by(desc('count'))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return [
                {"sender_id": row.sender_id, "count": row.count}
                for row in result.fetchall()
            ]
        except Exception as e:
            logger.error(f"[RawMessageRepository] 获取发送者统计失败: {e}")
            return []
