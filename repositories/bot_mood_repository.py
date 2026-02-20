"""
Bot 情绪 Repository — BotMood 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.psychological import BotMood


class BotMoodRepository(BaseRepository[BotMood]):
    """Bot 情绪 Repository

    BotMood 使用 (group_id, is_active) 索引来快速查找当前情绪。
    设置新情绪时需先将旧情绪设为非活跃。
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, BotMood)

    async def save(self, mood_data: Dict[str, Any]) -> Optional[BotMood]:
        """
        保存新情绪（自动将同群组的旧情绪设为非活跃）

        Args:
            mood_data: 情绪字段字典，必须包含 group_id, mood_type

        Returns:
            Optional[BotMood]: 创建的记录
        """
        group_id = mood_data.get('group_id')
        if not group_id:
            logger.error("[BotMoodRepository] 保存情绪失败: 缺少 group_id")
            return None

        try:
            # 先将该群组的活跃情绪设为非活跃
            deactivate_stmt = (
                update(BotMood)
                .where(and_(
                    BotMood.group_id == group_id,
                    BotMood.is_active == 1,
                ))
                .values(is_active=0, end_time=time.time())
            )
            await self.session.execute(deactivate_stmt)

            # 创建新的活跃情绪
            mood_data.setdefault('start_time', time.time())
            mood_data.setdefault('is_active', 1)
            mood = BotMood(**mood_data)
            self.session.add(mood)
            await self.session.commit()
            await self.session.refresh(mood)
            return mood
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[BotMoodRepository] 保存情绪失败: {e}")
            return None

    async def get_current(self, group_id: str) -> Optional[BotMood]:
        """
        获取当前活跃情绪

        Args:
            group_id: 群组 ID

        Returns:
            Optional[BotMood]: 当前情绪对象
        """
        try:
            stmt = (
                select(BotMood)
                .where(and_(
                    BotMood.group_id == group_id,
                    BotMood.is_active == 1,
                ))
                .order_by(desc(BotMood.start_time))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[BotMoodRepository] 获取当前情绪失败: {e}")
            return None

    async def get_history(
        self,
        group_id: str,
        limit: int = 20
    ) -> List[BotMood]:
        """
        获取情绪历史

        Args:
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[BotMood]: 情绪历史列表（按时间倒序）
        """
        try:
            stmt = (
                select(BotMood)
                .where(BotMood.group_id == group_id)
                .order_by(desc(BotMood.start_time))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[BotMoodRepository] 获取情绪历史失败: {e}")
            return []

    async def deactivate_all(self, group_id: str) -> int:
        """
        将指定群组的所有活跃情绪设为非活跃

        Args:
            group_id: 群组 ID

        Returns:
            int: 更新的行数
        """
        try:
            stmt = (
                update(BotMood)
                .where(and_(
                    BotMood.group_id == group_id,
                    BotMood.is_active == 1,
                ))
                .values(is_active=0, end_time=time.time())
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[BotMoodRepository] 停用情绪失败: {e}")
            return 0

    async def get_mood_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取情绪统计信息

        Args:
            group_id: 群组 ID

        Returns:
            Dict: {"total": ..., "mood_distribution": {type: count, ...}}
        """
        try:
            total_stmt = select(func.count()).select_from(BotMood).where(
                BotMood.group_id == group_id
            )
            total_result = await self.session.execute(total_stmt)
            total = total_result.scalar() or 0

            dist_stmt = (
                select(
                    BotMood.mood_type,
                    func.count().label('count')
                )
                .where(BotMood.group_id == group_id)
                .group_by(BotMood.mood_type)
            )
            dist_result = await self.session.execute(dist_stmt)
            distribution = {
                row.mood_type: row.count for row in dist_result.fetchall()
            }

            return {"total": total, "mood_distribution": distribution}
        except Exception as e:
            logger.error(f"[BotMoodRepository] 获取情绪统计失败: {e}")
            return {"total": 0, "mood_distribution": {}}
