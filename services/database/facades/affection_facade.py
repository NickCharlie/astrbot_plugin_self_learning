"""
好感度 Facade — 好感度与情绪状态的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.affection_repository import AffectionRepository
from ....repositories.bot_mood_repository import BotMoodRepository


class AffectionFacade(BaseFacade):
    """好感度与 Bot 情绪管理 Facade"""

    async def get_user_affection(
        self, group_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取用户好感度"""
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                affection = await repo.get_by_group_and_user(group_id, user_id)
                if affection:
                    return {
                        'group_id': affection.group_id,
                        'user_id': affection.user_id,
                        'affection_level': affection.affection_level,
                        'max_affection': affection.max_affection,
                        'created_at': affection.created_at,
                        'updated_at': affection.updated_at,
                    }
                return None
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 获取好感度失败: {e}")
            return None

    async def update_user_affection(
        self,
        group_id: str,
        user_id: str,
        new_level: int,
        change_reason: str = "",
        bot_mood: str = ""
    ) -> bool:
        """更新用户好感度"""
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                current = await repo.get_by_group_and_user(group_id, user_id)
                previous_level = current.affection_level if current else 0
                affection_delta = new_level - previous_level
                affection = await repo.update_level(
                    group_id, user_id, affection_delta, max_affection=100
                )
                return affection is not None
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 更新好感度失败: {e}")
            return False

    async def get_all_user_affections(self, group_id: str) -> List[Dict[str, Any]]:
        """获取群组所有用户好感度"""
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                affections = await repo.find_many(group_id=group_id)
                return [
                    {
                        'group_id': a.group_id,
                        'user_id': a.user_id,
                        'affection_level': a.affection_level,
                        'max_affection': a.max_affection,
                        'created_at': a.created_at,
                        'updated_at': a.updated_at,
                    }
                    for a in affections
                ]
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 获取所有好感度失败: {e}")
            return []

    async def get_total_affection(self, group_id: str) -> int:
        """获取群组总好感度"""
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                return await repo.get_total_affection(group_id)
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 获取总好感度失败: {e}")
            return 0

    async def save_bot_mood(
        self,
        group_id: str,
        mood_type: str,
        mood_intensity: float,
        mood_description: str,
        duration_hours: int = 24
    ) -> bool:
        """保存 Bot 情绪状态"""
        try:
            async with self.get_session() as session:
                repo = BotMoodRepository(session)
                mood = await repo.save({
                    'group_id': group_id,
                    'mood_type': mood_type,
                    'mood_intensity': mood_intensity,
                    'mood_description': mood_description,
                    'start_time': time.time(),
                })
                return mood is not None
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 保存情绪状态失败: {e}")
            return False

    async def get_current_bot_mood(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前活跃情绪"""
        try:
            async with self.get_session() as session:
                repo = BotMoodRepository(session)
                mood = await repo.get_current(group_id)
                if not mood:
                    return None
                return {
                    'mood_type': mood.mood_type,
                    'mood_intensity': mood.mood_intensity,
                    'mood_description': mood.mood_description,
                    'start_time': mood.start_time,
                    'end_time': mood.end_time,
                }
        except Exception as e:
            self._logger.error(f"[AffectionFacade] 获取当前情绪失败: {e}")
            return None
