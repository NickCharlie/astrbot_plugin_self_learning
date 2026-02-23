"""
情绪画像 Repository — EmotionProfile 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.psychological import EmotionProfile


class EmotionProfileRepository(BaseRepository[EmotionProfile]):
    """情绪画像 Repository

    EmotionProfile 以 (user_id, group_id) 唯一约束。
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, EmotionProfile)

    async def load(self, user_id: str, group_id: str) -> Optional[EmotionProfile]:
        """
        加载情绪画像

        Args:
            user_id: 用户 ID
            group_id: 群组 ID

        Returns:
            Optional[EmotionProfile]: 情绪画像对象
        """
        try:
            stmt = select(EmotionProfile).where(and_(
                EmotionProfile.user_id == user_id,
                EmotionProfile.group_id == group_id,
            ))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[EmotionProfileRepository] 加载情绪画像失败: {e}")
            return None

    async def save(self, profile_data: Dict[str, Any]) -> Optional[EmotionProfile]:
        """
        保存情绪画像（upsert：存在则更新，不存在则创建）

        Args:
            profile_data: 画像字段字典，必须包含 user_id 和 group_id

        Returns:
            Optional[EmotionProfile]: 保存后的记录
        """
        user_id = profile_data.get('user_id')
        group_id = profile_data.get('group_id')
        if not user_id or not group_id:
            logger.error("[EmotionProfileRepository] 保存画像失败: 缺少 user_id 或 group_id")
            return None

        try:
            existing = await self.load(user_id, group_id)
            if existing:
                for key, value in profile_data.items():
                    if key not in ('user_id', 'group_id', 'id') and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.last_updated = time.time()
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                profile_data.setdefault('last_updated', time.time())
                profile = EmotionProfile(**profile_data)
                self.session.add(profile)
                await self.session.commit()
                await self.session.refresh(profile)
                return profile
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[EmotionProfileRepository] 保存情绪画像失败: {e}")
            return None

    async def get_by_group(self, group_id: str) -> List[EmotionProfile]:
        """
        获取群组内所有情绪画像

        Args:
            group_id: 群组 ID

        Returns:
            List[EmotionProfile]: 情绪画像列表
        """
        try:
            stmt = select(EmotionProfile).where(
                EmotionProfile.group_id == group_id
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[EmotionProfileRepository] 获取群组情绪画像失败: {e}")
            return []

    async def get_by_user(self, user_id: str) -> List[EmotionProfile]:
        """
        获取用户在所有群组的情绪画像

        Args:
            user_id: 用户 ID

        Returns:
            List[EmotionProfile]: 情绪画像列表
        """
        try:
            stmt = select(EmotionProfile).where(
                EmotionProfile.user_id == user_id
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[EmotionProfileRepository] 获取用户情绪画像失败: {e}")
            return []

    async def count_all(self) -> int:
        """
        统计情绪画像总数

        Returns:
            int: 画像数量
        """
        try:
            stmt = select(func.count()).select_from(EmotionProfile)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[EmotionProfileRepository] 统计画像失败: {e}")
            return 0
