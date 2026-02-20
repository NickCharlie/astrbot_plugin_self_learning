"""
心理状态 Facade — 情绪画像与心理分析的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.emotion_profile_repository import EmotionProfileRepository


class PsychologicalFacade(BaseFacade):
    """心理状态管理 Facade"""

    async def load_emotion_profile(
        self, user_id: str, group_id: str
    ) -> Optional[Dict[str, Any]]:
        """加载情绪画像"""
        try:
            async with self.get_session() as session:
                repo = EmotionProfileRepository(session)
                ep = await repo.load(user_id, group_id)
                if not ep:
                    return None
                return {
                    'user_id': ep.user_id,
                    'group_id': ep.group_id,
                    'dominant_emotions': json.loads(ep.dominant_emotions) if ep.dominant_emotions else {},
                    'emotion_patterns': json.loads(ep.emotion_patterns) if ep.emotion_patterns else {},
                    'empathy_level': ep.empathy_level,
                    'emotional_stability': ep.emotional_stability,
                    'last_updated': ep.last_updated,
                }
        except Exception as e:
            self._logger.error(f"[PsychologicalFacade] 加载情绪画像失败: {e}")
            return None

    async def save_emotion_profile(
        self, user_id: str, group_id: str, profile: Dict[str, Any]
    ) -> bool:
        """保存情绪画像（upsert）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, and_
                from ....models.orm.psychological import EmotionProfile

                stmt = select(EmotionProfile).where(
                    and_(EmotionProfile.user_id == user_id, EmotionProfile.group_id == group_id)
                )
                result = await session.execute(stmt)
                ep = result.scalar_one_or_none()
                now = time.time()
                if ep:
                    ep.dominant_emotions = json.dumps(profile.get('dominant_emotions', {}), ensure_ascii=False)
                    ep.emotion_patterns = json.dumps(profile.get('emotion_patterns', {}), ensure_ascii=False)
                    ep.empathy_level = profile.get('empathy_level', 0.5)
                    ep.emotional_stability = profile.get('emotional_stability', 0.5)
                    ep.last_updated = now
                else:
                    ep = EmotionProfile(
                        user_id=user_id, group_id=group_id,
                        dominant_emotions=json.dumps(profile.get('dominant_emotions', {}), ensure_ascii=False),
                        emotion_patterns=json.dumps(profile.get('emotion_patterns', {}), ensure_ascii=False),
                        empathy_level=profile.get('empathy_level', 0.5),
                        emotional_stability=profile.get('emotional_stability', 0.5),
                        last_updated=now,
                    )
                    session.add(ep)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[PsychologicalFacade] 保存情绪画像失败: {e}")
            return False
