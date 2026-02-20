"""
用户画像 Repository — UserProfile 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.social_relation import UserProfile


class UserProfileRepository(BaseRepository[UserProfile]):
    """用户画像 Repository

    UserProfile 以 qq_id 为主键（String），不使用自增 ID。
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserProfile)

    async def load(self, qq_id: str) -> Optional[UserProfile]:
        """
        加载用户画像

        Args:
            qq_id: 用户 QQ 号

        Returns:
            Optional[UserProfile]: 用户画像对象
        """
        try:
            stmt = select(UserProfile).where(UserProfile.qq_id == qq_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[UserProfileRepository] 加载用户画像失败: {e}")
            return None

    async def save(self, profile_data: Dict[str, Any]) -> Optional[UserProfile]:
        """
        保存用户画像（upsert：存在则更新，不存在则创建）

        Args:
            profile_data: 画像字段字典，必须包含 qq_id

        Returns:
            Optional[UserProfile]: 保存后的记录
        """
        qq_id = profile_data.get('qq_id')
        if not qq_id:
            logger.error("[UserProfileRepository] 保存画像失败: 缺少 qq_id")
            return None

        try:
            existing = await self.load(qq_id)
            if existing:
                # 更新已有记录
                for key, value in profile_data.items():
                    if key != 'qq_id' and hasattr(existing, key):
                        setattr(existing, key, value)
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                # 创建新记录
                profile = UserProfile(**profile_data)
                self.session.add(profile)
                await self.session.commit()
                await self.session.refresh(profile)
                return profile
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[UserProfileRepository] 保存用户画像失败: {e}")
            return None

    async def get_all_profiles(self, limit: int = 100) -> List[UserProfile]:
        """
        获取所有用户画像

        Args:
            limit: 最大返回数量

        Returns:
            List[UserProfile]: 画像列表
        """
        try:
            stmt = select(UserProfile).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[UserProfileRepository] 获取所有画像失败: {e}")
            return []

    async def count_all(self) -> int:
        """
        统计用户画像总数

        Returns:
            int: 画像数量
        """
        try:
            stmt = select(func.count()).select_from(UserProfile)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[UserProfileRepository] 统计画像失败: {e}")
            return 0

    async def delete_profile(self, qq_id: str) -> bool:
        """
        删除用户画像

        Args:
            qq_id: 用户 QQ 号

        Returns:
            bool: 是否成功
        """
        try:
            profile = await self.load(qq_id)
            if profile:
                await self.session.delete(profile)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[UserProfileRepository] 删除画像失败: {e}")
            return False
