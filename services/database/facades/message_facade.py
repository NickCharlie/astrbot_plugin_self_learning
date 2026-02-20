"""
消息 Facade — 原始消息、筛选消息、Bot消息的业务入口
"""
import time
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.raw_message_repository import RawMessageRepository
from ....repositories.filtered_message_repository import FilteredMessageRepository
from ....repositories.bot_message_repository import BotMessageRepository


class MessageFacade(BaseFacade):
    """消息管理 Facade"""

    # ---- 原始消息 ----

    async def save_raw_message(self, message_data) -> int:
        """保存原始消息

        Args:
            message_data: 消息数据（对象或字典）

        Returns:
            int: 消息 ID（失败返回 0）
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.message import RawMessage

                if hasattr(message_data, '__dict__'):
                    data = message_data.__dict__
                else:
                    data = message_data

                raw_msg = RawMessage(
                    sender_id=str(data.get('sender_id', '')),
                    sender_name=data.get('sender_name', ''),
                    message=data.get('message', ''),
                    group_id=data.get('group_id', ''),
                    timestamp=int(data.get('timestamp', time.time())),
                    platform=data.get('platform', ''),
                    message_id=data.get('message_id'),
                    reply_to=data.get('reply_to'),
                    created_at=int(time.time()),
                    processed=False,
                )
                session.add(raw_msg)
                await session.commit()
                await session.refresh(raw_msg)
                return raw_msg.id
        except Exception as e:
            self._logger.error(f"[MessageFacade] 保存原始消息失败: {e}")
            return 0

    async def get_recent_raw_messages(
        self, group_id: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """获取最近的原始消息"""
        try:
            async with self.get_session() as session:
                repo = RawMessageRepository(session)
                messages = await repo.get_recent(group_id=group_id, limit=limit)
                return [
                    {
                        'id': msg.id, 'sender_id': msg.sender_id,
                        'sender_name': msg.sender_name, 'message': msg.message,
                        'group_id': msg.group_id, 'timestamp': msg.timestamp,
                        'platform': msg.platform, 'message_id': msg.message_id,
                        'reply_to': msg.reply_to, 'created_at': msg.created_at,
                        'processed': msg.processed,
                    }
                    for msg in messages
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取最近原始消息失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的最近原始消息: {e}") from e

    async def get_unprocessed_messages(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取未处理的原始消息"""
        try:
            async with self.get_session() as session:
                repo = RawMessageRepository(session)
                messages = await repo.get_unprocessed(limit=limit or 100)
                return [
                    {
                        'id': msg.id, 'sender_id': msg.sender_id,
                        'sender_name': msg.sender_name, 'message': msg.message,
                        'group_id': msg.group_id, 'platform': msg.platform,
                        'timestamp': msg.timestamp,
                    }
                    for msg in messages
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取未处理消息失败: {e}")
            raise RuntimeError(f"获取未处理消息失败: {e}") from e

    async def mark_messages_processed(self, message_ids: List[int]) -> bool:
        """批量标记消息为已处理"""
        if not message_ids:
            return True
        try:
            async with self.get_session() as session:
                repo = RawMessageRepository(session)
                count = await repo.mark_batch_processed(message_ids)
                return count > 0
        except Exception as e:
            self._logger.error(f"[MessageFacade] 标记已处理失败: {e}")
            return False

    async def get_messages_by_timerange(
        self, group_id: str, start_time: int, end_time: int, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """按时间范围获取消息"""
        return await self.get_messages_by_group_and_timerange(
            group_id, start_time, end_time, limit
        )

    async def get_messages_by_group_and_timerange(
        self, group_id: str, start_time: int, end_time: int, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """按群组和时间范围获取消息"""
        try:
            async with self.get_session() as session:
                repo = RawMessageRepository(session)
                messages = await repo.get_by_timerange(group_id, start_time, end_time, limit)
                return [
                    {
                        'id': msg.id, 'sender_id': msg.sender_id,
                        'sender_name': msg.sender_name, 'message': msg.message,
                        'group_id': msg.group_id, 'timestamp': msg.timestamp,
                    }
                    for msg in messages
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 按时间范围获取消息失败: {e}")
            return []

    async def get_messages_for_replay(
        self, group_id: str, days: int = 30, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取用于记忆重放的消息"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc, and_
                from ....models.orm.message import RawMessage

                cutoff_time = time.time() - (days * 24 * 3600)
                stmt = (
                    select(RawMessage)
                    .where(and_(
                        RawMessage.group_id == group_id,
                        RawMessage.timestamp > cutoff_time,
                        RawMessage.processed == True,  # noqa: E712
                    ))
                    .order_by(desc(RawMessage.timestamp))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                return [
                    {
                        'message_id': msg.id, 'message': msg.message,
                        'sender_id': msg.sender_id, 'group_id': msg.group_id,
                        'timestamp': msg.timestamp,
                    }
                    for msg in result.scalars().all()
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取记忆重放消息失败: {e}")
            return []

    # ---- 筛选消息 ----

    async def get_recent_filtered_messages(
        self, group_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取最近的筛选消息"""
        try:
            async with self.get_session() as session:
                repo = FilteredMessageRepository(session)
                messages = await repo.get_recent(group_id=group_id, limit=limit)
                return [
                    {
                        'id': msg.id, 'raw_message_id': msg.raw_message_id,
                        'message': msg.message, 'sender_id': msg.sender_id,
                        'group_id': msg.group_id, 'timestamp': msg.timestamp,
                        'confidence': msg.confidence, 'quality_scores': msg.quality_scores,
                        'filter_reason': msg.filter_reason, 'created_at': msg.created_at,
                        'processed': msg.processed,
                    }
                    for msg in messages
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取筛选消息失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的最近筛选消息: {e}") from e

    async def get_filtered_messages_for_learning(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取待学习的筛选消息"""
        try:
            async with self.get_session() as session:
                repo = FilteredMessageRepository(session)
                messages = await repo.get_for_learning(limit=limit)
                return [
                    {
                        'id': msg.id, 'message': msg.message,
                        'sender_id': msg.sender_id, 'group_id': msg.group_id,
                        'timestamp': msg.timestamp, 'confidence': msg.confidence,
                    }
                    for msg in messages
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取待学习筛选消息失败: {e}")
            return []

    async def add_filtered_message(self, filtered_data: Dict[str, Any]) -> int:
        """添加筛选后的消息"""
        try:
            async with self.get_session() as session:
                repo = FilteredMessageRepository(session)
                msg = await repo.add(filtered_data)
                return msg.id if msg else 0
        except Exception as e:
            self._logger.error(f"[MessageFacade] 添加筛选消息失败: {e}")
            return 0

    # ---- Bot 消息 ----

    async def save_bot_message(
        self, group_id: str, message: str, timestamp: int = None
    ) -> bool:
        """保存 Bot 消息"""
        try:
            async with self.get_session() as session:
                repo = BotMessageRepository(session)
                result = await repo.save({
                    'group_id': group_id,
                    'message': message,
                    'timestamp': timestamp or int(time.time()),
                })
                return result is not None
        except Exception as e:
            self._logger.error(f"[MessageFacade] 保存 Bot 消息失败: {e}")
            return False

    async def get_recent_bot_responses(
        self, group_id: str, limit: int = 10
    ) -> List[str]:
        """获取最近的 Bot 回复（仅文本）"""
        try:
            async with self.get_session() as session:
                repo = BotMessageRepository(session)
                messages = await repo.get_recent_responses(group_id, limit)
                return [msg.message for msg in messages]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取 Bot 回复失败: {e}")
            return []

    # ---- 统计 ----

    async def get_message_statistics(
        self, group_id: str = None
    ) -> Dict[str, Any]:
        """获取消息统计信息"""
        if not group_id:
            return await self.get_messages_statistics()

        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func, and_
                from ....models.orm.message import RawMessage, FilteredMessage

                total_stmt = select(func.count()).select_from(RawMessage).where(
                    RawMessage.group_id == group_id
                )
                total = (await session.execute(total_stmt)).scalar() or 0

                unprocessed_stmt = select(func.count()).select_from(RawMessage).where(
                    and_(RawMessage.group_id == group_id, RawMessage.processed == False)  # noqa: E712
                )
                unprocessed = (await session.execute(unprocessed_stmt)).scalar() or 0

                filtered_stmt = select(func.count()).select_from(FilteredMessage).where(
                    FilteredMessage.group_id == group_id
                )
                filtered = (await session.execute(filtered_stmt)).scalar() or 0

                return {
                    'total_messages': total,
                    'unprocessed_messages': unprocessed,
                    'filtered_messages': filtered,
                    'raw_messages': total,
                    'group_id': group_id,
                }
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取消息统计失败: {e}")
            return {
                'total_messages': 0, 'unprocessed_messages': 0,
                'filtered_messages': 0, 'raw_messages': 0, 'group_id': group_id,
            }

    async def get_messages_statistics(self) -> Dict[str, Any]:
        """获取全局消息统计"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.message import RawMessage, FilteredMessage, BotMessage

                raw_count = (await session.execute(
                    select(func.count()).select_from(RawMessage)
                )).scalar() or 0
                filtered_count = (await session.execute(
                    select(func.count()).select_from(FilteredMessage)
                )).scalar() or 0
                bot_count = (await session.execute(
                    select(func.count()).select_from(BotMessage)
                )).scalar() or 0

                return {
                    'total_messages': raw_count,
                    'raw_messages': raw_count,
                    'filtered_messages': filtered_count,
                    'bot_messages': bot_count,
                }
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取全局统计失败: {e}")
            return {
                'total_messages': 0, 'raw_messages': 0,
                'filtered_messages': 0, 'bot_messages': 0,
            }

    async def get_group_messages_statistics(
        self, group_id: str
    ) -> Dict[str, Any]:
        """获取群组消息统计"""
        return await self.get_message_statistics(group_id)

    async def get_group_user_statistics(
        self, group_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """获取群组用户消息统计"""
        try:
            async with self.get_session() as session:
                repo = RawMessageRepository(session)
                stats = await repo.get_sender_statistics(group_id, limit=50)
                return {
                    s['sender_id']: {'message_count': s['count']}
                    for s in stats
                }
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取用户统计失败: {e}")
            return {}

    async def get_groups_for_social_analysis(self) -> List[Dict[str, Any]]:
        """获取有消息记录的群组列表（用于社交分析）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.message import RawMessage

                stmt = (
                    select(
                        RawMessage.group_id,
                        func.count().label('message_count')
                    )
                    .group_by(RawMessage.group_id)
                    .order_by(func.count().desc())
                )
                result = await session.execute(stmt)
                return [
                    {'group_id': row.group_id, 'message_count': row.message_count}
                    for row in result.fetchall()
                ]
        except Exception as e:
            self._logger.error(f"[MessageFacade] 获取分析群组列表失败: {e}")
            return []
