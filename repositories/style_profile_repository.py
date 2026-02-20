"""
风格画像 Repository — StyleProfile 表的数据访问
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.expression import StyleProfile


class StyleProfileRepository(BaseRepository[StyleProfile]):
    """风格画像 Repository

    StyleProfile 以 profile_name 为逻辑键。
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, StyleProfile)

    async def load(self, profile_name: str) -> Optional[StyleProfile]:
        """
        加载风格画像

        Args:
            profile_name: 画像名称

        Returns:
            Optional[StyleProfile]: 风格画像对象
        """
        try:
            stmt = select(StyleProfile).where(
                StyleProfile.profile_name == profile_name
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[StyleProfileRepository] 加载风格画像失败: {e}")
            return None

    async def save(self, profile_data: Dict[str, Any]) -> Optional[StyleProfile]:
        """
        保存风格画像（upsert：存在则更新，不存在则创建）

        Args:
            profile_data: 画像字段字典，必须包含 profile_name

        Returns:
            Optional[StyleProfile]: 保存后的记录
        """
        profile_name = profile_data.get('profile_name')
        if not profile_name:
            logger.error("[StyleProfileRepository] 保存画像失败: 缺少 profile_name")
            return None

        try:
            existing = await self.load(profile_name)
            if existing:
                for key, value in profile_data.items():
                    if key not in ('profile_name', 'id') and hasattr(existing, key):
                        setattr(existing, key, value)
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                profile = StyleProfile(**profile_data)
                self.session.add(profile)
                await self.session.commit()
                await self.session.refresh(profile)
                return profile
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[StyleProfileRepository] 保存风格画像失败: {e}")
            return None

    async def get_all_profiles(self, limit: int = 100) -> List[StyleProfile]:
        """
        获取所有风格画像

        Args:
            limit: 最大返回数量

        Returns:
            List[StyleProfile]: 画像列表
        """
        try:
            stmt = select(StyleProfile).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[StyleProfileRepository] 获取所有画像失败: {e}")
            return []

    async def delete_profile(self, profile_name: str) -> bool:
        """
        删除风格画像

        Args:
            profile_name: 画像名称

        Returns:
            bool: 是否成功
        """
        try:
            profile = await self.load(profile_name)
            if profile:
                await self.session.delete(profile)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[StyleProfileRepository] 删除画像失败: {e}")
            return False

    async def count_all(self) -> int:
        """
        统计风格画像总数

        Returns:
            int: 画像数量
        """
        try:
            stmt = select(func.count()).select_from(StyleProfile)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[StyleProfileRepository] 统计画像失败: {e}")
            return 0
