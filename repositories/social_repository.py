"""
社交关系系统相关的 Repository
"""
import time
from sqlalchemy import select, and_
from typing import Optional, List
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import (
    UserSocialProfile,
    UserSocialRelationComponent,
    SocialRelationHistory
)


class SocialProfileRepository(BaseRepository[UserSocialProfile]):
    """用户社交档案 Repository"""

    def __init__(self, session):
        super().__init__(session, UserSocialProfile)

    async def get_or_create(
        self,
        group_id: str,
        user_id: str
    ) -> UserSocialProfile:
        """
        获取或创建社交档案

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            UserSocialProfile: 社交档案对象
        """
        profile = await self.find_one(group_id=group_id, user_id=user_id)

        if not profile:
            profile = await self.create(
                group_id=group_id,
                user_id=user_id,
                total_relation_value=0.0,
                interaction_frequency=0.0,
                last_interaction_time=int(time.time()),
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

        return profile

    async def update_interaction(
        self,
        group_id: str,
        user_id: str,
        relation_delta: float = 0.0,
        frequency_delta: float = 0.0
    ) -> Optional[UserSocialProfile]:
        """
        更新互动信息

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            relation_delta: 关系值变化
            frequency_delta: 频率变化

        Returns:
            Optional[UserSocialProfile]: 更新后的档案
        """
        profile = await self.get_or_create(group_id, user_id)

        profile.total_relation_value += relation_delta
        profile.interaction_frequency += frequency_delta
        profile.last_interaction_time = int(time.time())
        profile.updated_at = int(time.time())

        return await self.update(profile)

    async def get_top_relations(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[UserSocialProfile]:
        """
        获取关系值最高的用户

        Args:
            group_id: 群组 ID
            limit: 返回数量

        Returns:
            List[UserSocialProfile]: 社交档案列表
        """
        try:
            stmt = select(UserSocialProfile).where(
                UserSocialProfile.group_id == group_id
            ).order_by(
                UserSocialProfile.total_relation_value.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[SocialProfileRepository] 获取关系排行失败: {e}")
            return []


class SocialRelationComponentRepository(BaseRepository[UserSocialRelationComponent]):
    """社交关系组件 Repository"""

    def __init__(self, session):
        super().__init__(session, UserSocialRelationComponent)

    async def get_components(
        self,
        profile_id: int
    ) -> List[UserSocialRelationComponent]:
        """
        获取档案的所有关系组件

        Args:
            profile_id: 档案 ID

        Returns:
            List[UserSocialRelationComponent]: 组件列表
        """
        return await self.find_many(profile_id=profile_id)

    async def update_component(
        self,
        profile_id: int,
        component_name: str,
        value: float,
        weight: float = 1.0
    ) -> Optional[UserSocialRelationComponent]:
        """
        更新关系组件

        Args:
            profile_id: 档案 ID
            component_name: 组件名称
            value: 组件值
            weight: 权重

        Returns:
            Optional[UserSocialRelationComponent]: 组件对象
        """
        component = await self.find_one(
            profile_id=profile_id,
            component_name=component_name
        )

        if component:
            component.value = value
            component.weight = weight
            component.updated_at = int(time.time())
            return await self.update(component)
        else:
            return await self.create(
                profile_id=profile_id,
                component_name=component_name,
                value=value,
                weight=weight,
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

    async def get_weighted_sum(self, profile_id: int) -> float:
        """
        计算加权总和

        Args:
            profile_id: 档案 ID

        Returns:
            float: 加权总和
        """
        components = await self.get_components(profile_id)
        return sum(c.value * c.weight for c in components)


class SocialRelationHistoryRepository(BaseRepository[SocialRelationHistory]):
    """社交关系历史 Repository"""

    def __init__(self, session):
        super().__init__(session, SocialRelationHistory)

    async def add_history(
        self,
        profile_id: int,
        interaction_type: str,
        relation_change: float,
        context: str = None
    ) -> Optional[SocialRelationHistory]:
        """
        添加历史记录

        Args:
            profile_id: 档案 ID
            interaction_type: 互动类型
            relation_change: 关系变化
            context: 上下文信息

        Returns:
            Optional[SocialRelationHistory]: 历史记录
        """
        return await self.create(
            profile_id=profile_id,
            interaction_type=interaction_type,
            relation_change=relation_change,
            context=context,
            timestamp=int(time.time())
        )

    async def get_recent_history(
        self,
        profile_id: int,
        limit: int = 50
    ) -> List[SocialRelationHistory]:
        """
        获取最近的历史记录

        Args:
            profile_id: 档案 ID
            limit: 返回数量

        Returns:
            List[SocialRelationHistory]: 历史记录列表
        """
        try:
            stmt = select(SocialRelationHistory).where(
                SocialRelationHistory.profile_id == profile_id
            ).order_by(
                SocialRelationHistory.timestamp.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[SocialRelationHistoryRepository] 获取历史记录失败: {e}")
            return []

    async def get_statistics(
        self,
        profile_id: int,
        days: int = 30
    ) -> dict:
        """
        获取统计信息

        Args:
            profile_id: 档案 ID
            days: 统计天数

        Returns:
            dict: 统计信息
        """
        try:
            from sqlalchemy import func

            cutoff_time = int(time.time()) - (days * 24 * 3600)

            # 统计互动次数
            count_stmt = select(func.count()).where(
                and_(
                    SocialRelationHistory.profile_id == profile_id,
                    SocialRelationHistory.timestamp >= cutoff_time
                )
            )
            count_result = await self.session.execute(count_stmt)
            interaction_count = count_result.scalar() or 0

            # 统计关系变化总和
            sum_stmt = select(func.sum(SocialRelationHistory.relation_change)).where(
                and_(
                    SocialRelationHistory.profile_id == profile_id,
                    SocialRelationHistory.timestamp >= cutoff_time
                )
            )
            sum_result = await self.session.execute(sum_stmt)
            relation_sum = sum_result.scalar() or 0.0

            return {
                'interaction_count': interaction_count,
                'total_relation_change': relation_sum,
                'days': days
            }

        except Exception as e:
            logger.error(f"[SocialRelationHistoryRepository] 获取统计信息失败: {e}")
            return {
                'interaction_count': 0,
                'total_relation_change': 0.0,
                'days': days
            }
