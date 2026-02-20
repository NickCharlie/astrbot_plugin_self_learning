"""
用户偏好 Repository — UserPreferences 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.social_relation import UserPreferences


class UserPreferencesRepository(BaseRepository[UserPreferences]):
    """用户偏好 Repository

    UserPreferences 以 (user_id, group_id) 唯一约束。
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserPreferences)

    async def load(self, user_id: str, group_id: str) -> Optional[UserPreferences]:
        """
        加载用户偏好

        Args:
            user_id: 用户 ID
            group_id: 群组 ID

        Returns:
            Optional[UserPreferences]: 偏好对象
        """
        try:
            stmt = select(UserPreferences).where(and_(
                UserPreferences.user_id == user_id,
                UserPreferences.group_id == group_id,
            ))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[UserPreferencesRepository] 加载偏好失败: {e}")
            return None

    async def save(self, pref_data: Dict[str, Any]) -> Optional[UserPreferences]:
        """
        保存用户偏好（upsert：存在则更新，不存在则创建）

        Args:
            pref_data: 偏好字段字典，必须包含 user_id 和 group_id

        Returns:
            Optional[UserPreferences]: 保存后的记录
        """
        user_id = pref_data.get('user_id')
        group_id = pref_data.get('group_id')
        if not user_id or not group_id:
            logger.error("[UserPreferencesRepository] 保存偏好失败: 缺少 user_id 或 group_id")
            return None

        try:
            existing = await self.load(user_id, group_id)
            if existing:
                for key, value in pref_data.items():
                    if key not in ('user_id', 'group_id', 'id') and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = time.time()
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                pref_data.setdefault('updated_at', time.time())
                pref = UserPreferences(**pref_data)
                self.session.add(pref)
                await self.session.commit()
                await self.session.refresh(pref)
                return pref
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[UserPreferencesRepository] 保存偏好失败: {e}")
            return None

    async def get_by_user(self, user_id: str) -> List[UserPreferences]:
        """
        获取用户在所有群组的偏好

        Args:
            user_id: 用户 ID

        Returns:
            List[UserPreferences]: 偏好列表
        """
        try:
            stmt = select(UserPreferences).where(
                UserPreferences.user_id == user_id
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[UserPreferencesRepository] 获取用户偏好失败: {e}")
            return []

    async def get_by_group(self, group_id: str) -> List[UserPreferences]:
        """
        获取群组内所有用户的偏好

        Args:
            group_id: 群组 ID

        Returns:
            List[UserPreferences]: 偏好列表
        """
        try:
            stmt = select(UserPreferences).where(
                UserPreferences.group_id == group_id
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[UserPreferencesRepository] 获取群组偏好失败: {e}")
            return []

    async def count_all(self) -> int:
        """
        统计偏好总数

        Returns:
            int: 偏好数量
        """
        try:
            stmt = select(func.count()).select_from(UserPreferences)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[UserPreferencesRepository] 统计偏好失败: {e}")
            return 0
