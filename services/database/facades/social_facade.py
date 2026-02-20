"""
社交关系 Facade — 用户画像、偏好、社交关系网络的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.user_profile_repository import UserProfileRepository
from ....repositories.user_preferences_repository import UserPreferencesRepository


class SocialFacade(BaseFacade):
    """社交关系管理 Facade"""

    # ---- 用户画像 ----

    async def load_user_profile(self, qq_id: str) -> Optional[Dict[str, Any]]:
        """加载用户画像"""
        try:
            async with self.get_session() as session:
                from ....models.orm.social_relation import UserProfile
                profile = await session.get(UserProfile, qq_id)
                if not profile:
                    return None
                return {
                    'qq_id': profile.qq_id,
                    'qq_name': profile.qq_name,
                    'nicknames': json.loads(profile.nicknames) if profile.nicknames else [],
                    'activity_pattern': json.loads(profile.activity_pattern) if profile.activity_pattern else {},
                    'communication_style': json.loads(profile.communication_style) if profile.communication_style else {},
                    'topic_preferences': json.loads(profile.topic_preferences) if profile.topic_preferences else {},
                    'emotional_tendency': json.loads(profile.emotional_tendency) if profile.emotional_tendency else {},
                    'last_active': profile.last_active,
                }
        except Exception as e:
            self._logger.error(f"[SocialFacade] 加载用户画像失败: {e}")
            return None

    async def save_user_profile(self, qq_id: str, profile_data: Dict[str, Any]) -> bool:
        """保存用户画像（upsert）"""
        try:
            async with self.get_session() as session:
                from ....models.orm.social_relation import UserProfile
                profile = await session.get(UserProfile, qq_id)
                if profile:
                    profile.qq_name = profile_data.get('qq_name', profile.qq_name)
                    profile.nicknames = json.dumps(profile_data.get('nicknames', []), ensure_ascii=False)
                    profile.activity_pattern = json.dumps(profile_data.get('activity_pattern', {}), ensure_ascii=False)
                    profile.communication_style = json.dumps(profile_data.get('communication_style', {}), ensure_ascii=False)
                    profile.topic_preferences = json.dumps(profile_data.get('topic_preferences', {}), ensure_ascii=False)
                    profile.emotional_tendency = json.dumps(profile_data.get('emotional_tendency', {}), ensure_ascii=False)
                    profile.last_active = profile_data.get('last_active', time.time())
                else:
                    profile = UserProfile(
                        qq_id=qq_id,
                        qq_name=profile_data.get('qq_name', ''),
                        nicknames=json.dumps(profile_data.get('nicknames', []), ensure_ascii=False),
                        activity_pattern=json.dumps(profile_data.get('activity_pattern', {}), ensure_ascii=False),
                        communication_style=json.dumps(profile_data.get('communication_style', {}), ensure_ascii=False),
                        topic_preferences=json.dumps(profile_data.get('topic_preferences', {}), ensure_ascii=False),
                        emotional_tendency=json.dumps(profile_data.get('emotional_tendency', {}), ensure_ascii=False),
                        last_active=profile_data.get('last_active', time.time()),
                    )
                    session.add(profile)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[SocialFacade] 保存用户画像失败: {e}")
            return False

    # ---- 用户偏好 ----

    async def load_user_preferences(
        self, user_id: str, group_id: str
    ) -> Optional[Dict[str, Any]]:
        """加载用户偏好"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, and_
                from ....models.orm.social_relation import UserPreferences
                stmt = select(UserPreferences).where(
                    and_(UserPreferences.user_id == user_id, UserPreferences.group_id == group_id)
                )
                result = await session.execute(stmt)
                pref = result.scalar_one_or_none()
                if not pref:
                    return None
                return {
                    'user_id': pref.user_id,
                    'group_id': pref.group_id,
                    'favorite_topics': json.loads(pref.favorite_topics) if pref.favorite_topics else [],
                    'interaction_style': json.loads(pref.interaction_style) if pref.interaction_style else {},
                    'learning_preferences': json.loads(pref.learning_preferences) if pref.learning_preferences else {},
                    'adaptive_rate': pref.adaptive_rate,
                }
        except Exception as e:
            self._logger.error(f"[SocialFacade] 加载用户偏好失败: {e}")
            return None

    async def save_user_preferences(
        self, user_id: str, group_id: str, prefs: Dict[str, Any]
    ) -> bool:
        """保存用户偏好（upsert）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, and_
                from ....models.orm.social_relation import UserPreferences
                stmt = select(UserPreferences).where(
                    and_(UserPreferences.user_id == user_id, UserPreferences.group_id == group_id)
                )
                result = await session.execute(stmt)
                pref = result.scalar_one_or_none()
                now = time.time()
                if pref:
                    pref.favorite_topics = json.dumps(prefs.get('favorite_topics', []), ensure_ascii=False)
                    pref.interaction_style = json.dumps(prefs.get('interaction_style', {}), ensure_ascii=False)
                    pref.learning_preferences = json.dumps(prefs.get('learning_preferences', {}), ensure_ascii=False)
                    pref.adaptive_rate = prefs.get('adaptive_rate', 0.5)
                    pref.updated_at = now
                else:
                    pref = UserPreferences(
                        user_id=user_id, group_id=group_id,
                        favorite_topics=json.dumps(prefs.get('favorite_topics', []), ensure_ascii=False),
                        interaction_style=json.dumps(prefs.get('interaction_style', {}), ensure_ascii=False),
                        learning_preferences=json.dumps(prefs.get('learning_preferences', {}), ensure_ascii=False),
                        adaptive_rate=prefs.get('adaptive_rate', 0.5),
                        updated_at=now,
                    )
                    session.add(pref)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[SocialFacade] 保存用户偏好失败: {e}")
            return False

    # ---- 社交关系 ----

    async def get_social_relations_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """获取群组的社交关系列表

        返回格式兼容 SocialService/SocialRelationAnalyzer 期望的
        from_user/to_user 键名。
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.social_relation import UserSocialRelationComponent

                stmt = select(UserSocialRelationComponent).where(
                    UserSocialRelationComponent.group_id == group_id
                )
                result = await session.execute(stmt)
                components = result.scalars().all()
                return [
                    {
                        'from_user': c.from_user_id,
                        'to_user': c.to_user_id,
                        'relation_type': c.relation_type,
                        'strength': c.value,
                        'frequency': c.frequency,
                        'last_interaction': c.last_interaction,
                        'description': c.description,
                    }
                    for c in components
                ]
        except Exception as e:
            self._logger.error(f"[SocialFacade] 获取社交关系失败: {e}")
            return []

    async def get_social_relationships(self, group_id: str) -> List[Dict[str, Any]]:
        """获取社交关系（别名）"""
        return await self.get_social_relations_by_group(group_id)

    async def load_social_graph(self, group_id: str) -> List[Dict[str, Any]]:
        """加载社交关系图（别名）"""
        return await self.get_social_relations_by_group(group_id)

    async def save_social_relation(
        self, group_id: str, relation_data: Dict[str, Any]
    ) -> bool:
        """保存社交关系

        接受 SocialRelationAnalyzer 传入的 from_user/to_user 格式，
        映射到 ORM 模型的 from_user_id/to_user_id 列。
        """
        try:
            async with self.get_session() as session:
                from ....models.orm.social_relation import UserSocialRelationComponent
                import time as _time

                now = int(_time.time())
                component = UserSocialRelationComponent(
                    profile_id=0,  # 无关联 profile 时使用占位值
                    from_user_id=relation_data.get('from_user', relation_data.get('from_user_id', '')),
                    to_user_id=relation_data.get('to_user', relation_data.get('to_user_id', '')),
                    group_id=group_id,
                    relation_type=relation_data.get('relation_type', 'interaction'),
                    value=relation_data.get('strength', 0.5),
                    frequency=relation_data.get('frequency', 1),
                    last_interaction=relation_data.get('last_interaction', now) if isinstance(
                        relation_data.get('last_interaction'), (int, float)
                    ) else now,
                    description=relation_data.get('relation_name', ''),
                    created_at=now,
                )
                session.add(component)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[SocialFacade] 保存社交关系失败: {e}")
            return False

    async def get_user_social_relations(
        self, group_id: str, user_id: str
    ) -> Dict[str, Any]:
        """获取用户的社交关系"""
        try:
            async with self.get_session() as session:
                from ....repositories.social_repository import SocialRelationComponentRepository
                repo = SocialRelationComponentRepository(session)
                from sqlalchemy import select, or_
                from ....models.orm.social_relation import UserSocialRelationComponent

                stmt = select(UserSocialRelationComponent).where(
                    UserSocialRelationComponent.group_id == group_id,
                    or_(
                        UserSocialRelationComponent.from_user_id == user_id,
                        UserSocialRelationComponent.to_user_id == user_id,
                    ),
                )
                result = await session.execute(stmt)
                relations = result.scalars().all()
                return {
                    'user_id': user_id,
                    'group_id': group_id,
                    'relations': [self._row_to_dict(r) for r in relations],
                }
        except Exception as e:
            self._logger.error(f"[SocialFacade] 获取用户社交关系失败: {e}")
            return {'user_id': user_id, 'group_id': group_id, 'relations': []}
