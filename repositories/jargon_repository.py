"""
黑话相关的 Repository
提供黑话数据的访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, or_
from typing import List, Optional, Dict, Any
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import Jargon


class JargonRepository(BaseRepository[Jargon]):
    """黑话 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Jargon)

    async def get_recent_jargon_list(
        self,
        chat_id: Optional[str] = None,
        limit: int = 20,
        only_confirmed: bool = True
    ) -> List[Jargon]:
        """
        获取最近学习到的黑话列表

        Args:
            chat_id: 群组ID (None表示获取所有)
            limit: 返回数量限制
            only_confirmed: 是否只返回已确认的黑话

        Returns:
            List[Jargon]: 黑话列表
        """
        try:
            conditions = []

            if chat_id:
                conditions.append(Jargon.chat_id == chat_id)

            if only_confirmed:
                conditions.append(Jargon.is_jargon == True)

            stmt = select(Jargon)
            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.order_by(desc(Jargon.updated_at)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[JargonRepository] 获取黑话列表失败: {e}")
            return []

    async def get_jargon_statistics(
        self,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取黑话学习统计信息

        Args:
            chat_id: 群组ID (None表示获取全局统计)

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        try:
            if chat_id:
                # 群组统计
                stmt = select(
                    func.count().label('total'),
                    func.count(Jargon.id).filter(Jargon.is_jargon == True).label('confirmed_jargon'),
                    func.count(Jargon.id).filter(Jargon.is_complete == True).label('completed'),
                    func.sum(Jargon.count).label('total_occurrences'),
                    func.avg(Jargon.count).label('avg_count')
                ).where(Jargon.chat_id == chat_id)

                result = await self.session.execute(stmt)
                row = result.fetchone()

                return {
                    'total_candidates': int(row.total) if row.total else 0,
                    'confirmed_jargon': int(row.confirmed_jargon) if row.confirmed_jargon else 0,
                    'completed_inference': int(row.completed) if row.completed else 0,
                    'total_occurrences': int(row.total_occurrences) if row.total_occurrences else 0,
                    'average_count': round(float(row.avg_count), 1) if row.avg_count else 0.0
                }
            else:
                # 全局统计
                stmt = select(
                    func.count().label('total'),
                    func.count(Jargon.id).filter(Jargon.is_jargon == True).label('confirmed_jargon'),
                    func.count(Jargon.id).filter(Jargon.is_complete == True).label('completed'),
                    func.sum(Jargon.count).label('total_occurrences'),
                    func.avg(Jargon.count).label('avg_count'),
                    func.count(func.distinct(Jargon.chat_id)).label('active_groups')
                )

                result = await self.session.execute(stmt)
                row = result.fetchone()

                return {
                    'total_candidates': int(row.total) if row.total else 0,
                    'confirmed_jargon': int(row.confirmed_jargon) if row.confirmed_jargon else 0,
                    'completed_inference': int(row.completed) if row.completed else 0,
                    'total_occurrences': int(row.total_occurrences) if row.total_occurrences else 0,
                    'average_count': round(float(row.avg_count), 1) if row.avg_count else 0.0,
                    'active_groups': int(row.active_groups) if row.active_groups else 0
                }

        except Exception as e:
            logger.error(f"[JargonRepository] 获取黑话统计失败: {e}")
            return {
                'total_candidates': 0,
                'confirmed_jargon': 0,
                'completed_inference': 0,
                'total_occurrences': 0,
                'average_count': 0.0,
                'active_groups': 0
            }

    async def get_by_content_and_chat(
        self,
        content: str,
        chat_id: str
    ) -> Optional[Jargon]:
        """
        根据内容和群组ID获取黑话

        Args:
            content: 黑话内容
            chat_id: 群组ID

        Returns:
            Optional[Jargon]: 黑话记录
        """
        try:
            stmt = select(Jargon).where(
                and_(
                    Jargon.content == content,
                    Jargon.chat_id == chat_id
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[JargonRepository] 根据内容获取黑话失败: {e}")
            return None

    async def update_jargon_status(
        self,
        jargon_id: int,
        is_jargon: Optional[bool] = None,
        is_complete: Optional[bool] = None,
        meaning: Optional[str] = None
    ) -> bool:
        """
        更新黑话状态

        Args:
            jargon_id: 黑话ID
            is_jargon: 是否为黑话
            is_complete: 是否完成推理
            meaning: 含义

        Returns:
            bool: 是否成功
        """
        try:
            update_data = {}
            if is_jargon is not None:
                update_data['is_jargon'] = is_jargon
            if is_complete is not None:
                update_data['is_complete'] = is_complete
            if meaning is not None:
                update_data['meaning'] = meaning

            if update_data:
                import time
                update_data['updated_at'] = int(time.time())
                return await self.update(jargon_id, **update_data)
            return True

        except Exception as e:
            logger.error(f"[JargonRepository] 更新黑话状态失败: {e}")
            return False

    async def increment_usage_count(
        self,
        jargon_id: int,
        increment: int = 1
    ) -> bool:
        """
        增加黑话使用次数

        Args:
            jargon_id: 黑话ID
            increment: 增量

        Returns:
            bool: 是否成功
        """
        try:
            jargon = await self.get_by_id(jargon_id)
            if not jargon:
                return False

            import time
            return await self.update(
                jargon_id,
                count=jargon.count + increment,
                updated_at=int(time.time())
            )

        except Exception as e:
            logger.error(f"[JargonRepository] 增加使用次数失败: {e}")
            return False
