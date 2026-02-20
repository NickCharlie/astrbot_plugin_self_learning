"""
Bot 消息 Repository — BotMessage 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, delete
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.message import BotMessage


class BotMessageRepository(BaseRepository[BotMessage]):
    """Bot 消息 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotMessage)

    async def save(self, message_data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        保存一条 Bot 消息

        Args:
            message_data: 消息字段字典，包含 group_id, message, timestamp 等

        Returns:
            Optional[BotMessage]: 创建的记录
        """
        try:
            now = int(time.time())
            return await self.create(
                group_id=message_data.get('group_id', ''),
                message=message_data.get('message', ''),
                timestamp=message_data.get('timestamp', now),
                created_at=now,
            )
        except Exception as e:
            logger.error(f"[BotMessageRepository] 保存 Bot 消息失败: {e}")
            return None

    async def get_recent_responses(
        self,
        group_id: str,
        limit: int = 50
    ) -> List[BotMessage]:
        """
        获取最近的 Bot 回复

        Args:
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[BotMessage]: Bot 消息列表（按时间倒序）
        """
        try:
            stmt = (
                select(BotMessage)
                .where(BotMessage.group_id == group_id)
                .order_by(desc(BotMessage.timestamp))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[BotMessageRepository] 获取最近 Bot 回复失败: {e}")
            return []

    async def get_statistics(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 Bot 消息统计信息

        Args:
            group_id: 群组 ID（为 None 时统计全部）

        Returns:
            Dict: {"total": ..., "groups": ...}
        """
        try:
            # 总数
            total_stmt = select(func.count()).select_from(BotMessage)
            if group_id:
                total_stmt = total_stmt.where(BotMessage.group_id == group_id)
            total_result = await self.session.execute(total_stmt)
            total = total_result.scalar() or 0

            # 按群组统计
            group_stmt = (
                select(
                    BotMessage.group_id,
                    func.count().label('count')
                )
                .group_by(BotMessage.group_id)
                .order_by(desc('count'))
            )
            if group_id:
                group_stmt = group_stmt.where(BotMessage.group_id == group_id)

            group_result = await self.session.execute(group_stmt)
            groups = [
                {"group_id": row.group_id, "count": row.count}
                for row in group_result.fetchall()
            ]

            return {"total": total, "groups": groups}
        except Exception as e:
            logger.error(f"[BotMessageRepository] 获取统计信息失败: {e}")
            return {"total": 0, "groups": []}

    async def count_all(self, group_id: Optional[str] = None) -> int:
        """
        统计 Bot 消息总数

        Args:
            group_id: 群组 ID（为 None 时统计全部）

        Returns:
            int: 消息数量
        """
        try:
            stmt = select(func.count()).select_from(BotMessage)
            if group_id:
                stmt = stmt.where(BotMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[BotMessageRepository] 统计消息失败: {e}")
            return 0

    async def delete_by_group(self, group_id: str) -> int:
        """
        删除指定群组的所有 Bot 消息

        Args:
            group_id: 群组 ID

        Returns:
            int: 删除的行数
        """
        try:
            stmt = delete(BotMessage).where(BotMessage.group_id == group_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[BotMessageRepository] 删除群组 Bot 消息失败: {e}")
            return 0
