"""
好感度相关的 Repository
"""
import time
from sqlalchemy import select, and_
from typing import Optional, List, Dict
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import (
    UserAffection,
    AffectionInteraction,
    UserConversationHistory,
    UserDiversity
)


class AffectionRepository(BaseRepository[UserAffection]):
    """好感度 Repository"""

    def __init__(self, session):
        super().__init__(session, UserAffection)

    async def get_by_group_and_user(
        self,
        group_id: str,
        user_id: str
    ) -> Optional[UserAffection]:
        """
        根据群组和用户获取好感度

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            Optional[UserAffection]: 好感度对象
        """
        return await self.find_one(group_id=group_id, user_id=user_id)

    async def update_level(
        self,
        group_id: str,
        user_id: str,
        delta: int,
        max_affection: int = 100
    ) -> UserAffection:
        """
        更新好感度等级

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            delta: 好感度变化量
            max_affection: 最大好感度

        Returns:
            UserAffection: 更新后的好感度对象
        """
        affection = await self.get_by_group_and_user(group_id, user_id)

        if affection:
            # 更新现有记录
            affection.affection_level = min(
                max_affection,
                max(0, affection.affection_level + delta)
            )
            affection.updated_at = int(time.time())
            return await self.update(affection)
        else:
            # 创建新记录
            return await self.create(
                group_id=group_id,
                user_id=user_id,
                affection_level=max(0, delta),
                max_affection=max_affection,
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

    async def get_top_users(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[UserAffection]:
        """
        获取好感度最高的用户

        Args:
            group_id: 群组 ID
            limit: 返回数量

        Returns:
            List[UserAffection]: 好感度列表
        """
        try:
            stmt = select(UserAffection).where(
                UserAffection.group_id == group_id
            ).order_by(
                UserAffection.affection_level.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[AffectionRepository] 获取好感度排行失败: {e}")
            return []

    async def get_total_affection(self, group_id: str) -> int:
        """
        获取群组总好感度

        Args:
            group_id: 群组 ID

        Returns:
            int: 总好感度
        """
        try:
            from sqlalchemy import func

            stmt = select(func.sum(UserAffection.affection_level)).where(
                UserAffection.group_id == group_id
            )

            result = await self.session.execute(stmt)
            return result.scalar() or 0

        except Exception as e:
            logger.error(f"[AffectionRepository] 获取总好感度失败: {e}")
            return 0


class InteractionRepository(BaseRepository[AffectionInteraction]):
    """好感度互动 Repository"""

    def __init__(self, session):
        super().__init__(session, AffectionInteraction)

    async def create_interaction(
        self,
        group_id: str,
        user_id: str,
        interaction_type: str,
        affection_delta: int,
        message: str = None
    ) -> Optional[AffectionInteraction]:
        """
        创建互动记录

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            interaction_type: 互动类型
            affection_delta: 好感度变化
            message: 消息内容

        Returns:
            Optional[AffectionInteraction]: 互动记录
        """
        return await self.create(
            group_id=group_id,
            user_id=user_id,
            interaction_type=interaction_type,
            affection_delta=affection_delta,
            message=message,
            timestamp=int(time.time())
        )

    async def get_recent_interactions(
        self,
        group_id: str,
        user_id: str,
        limit: int = 50
    ) -> List[AffectionInteraction]:
        """
        获取最近的互动记录

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            limit: 返回数量

        Returns:
            List[AffectionInteraction]: 互动记录列表
        """
        try:
            stmt = select(AffectionInteraction).where(
                and_(
                    AffectionInteraction.group_id == group_id,
                    AffectionInteraction.user_id == user_id
                )
            ).order_by(
                AffectionInteraction.timestamp.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[InteractionRepository] 获取互动记录失败: {e}")
            return []


class ConversationHistoryRepository(BaseRepository[UserConversationHistory]):
    """对话历史 Repository"""

    def __init__(self, session):
        super().__init__(session, UserConversationHistory)

    async def add_message(
        self,
        group_id: str,
        user_id: str,
        message: str,
        role: str = "user"
    ) -> Optional[UserConversationHistory]:
        """
        添加对话消息

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            message: 消息内容
            role: 角色 (user/assistant)

        Returns:
            Optional[UserConversationHistory]: 对话记录
        """
        return await self.create(
            group_id=group_id,
            user_id=user_id,
            message=message,
            role=role,
            timestamp=int(time.time())
        )

    async def get_recent_messages(
        self,
        group_id: str,
        user_id: str,
        limit: int = 20
    ) -> List[UserConversationHistory]:
        """
        获取最近的对话记录

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            limit: 返回数量

        Returns:
            List[UserConversationHistory]: 对话记录列表
        """
        try:
            stmt = select(UserConversationHistory).where(
                and_(
                    UserConversationHistory.group_id == group_id,
                    UserConversationHistory.user_id == user_id
                )
            ).order_by(
                UserConversationHistory.timestamp.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            # 反转顺序，使其按时间正序排列
            return list(reversed(list(result.scalars().all())))

        except Exception as e:
            logger.error(f"[ConversationHistoryRepository] 获取对话历史失败: {e}")
            return []

    async def clear_old_messages(
        self,
        group_id: str,
        user_id: str,
        keep_count: int = 100
    ) -> int:
        """
        清理旧消息，只保留最新的 N 条

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            keep_count: 保留数量

        Returns:
            int: 删除的记录数
        """
        try:
            # 查询要保留的最小 ID
            stmt = select(UserConversationHistory.id).where(
                and_(
                    UserConversationHistory.group_id == group_id,
                    UserConversationHistory.user_id == user_id
                )
            ).order_by(
                UserConversationHistory.timestamp.desc()
            ).limit(keep_count)

            result = await self.session.execute(stmt)
            keep_ids = [row[0] for row in result.fetchall()]

            if not keep_ids:
                return 0

            # 删除不在保留列表中的记录
            from sqlalchemy import delete

            stmt = delete(UserConversationHistory).where(
                and_(
                    UserConversationHistory.group_id == group_id,
                    UserConversationHistory.user_id == user_id,
                    UserConversationHistory.id.notin_(keep_ids)
                )
            )

            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[ConversationHistoryRepository] 清理旧消息失败: {e}")
            return 0


class DiversityRepository(BaseRepository[UserDiversity]):
    """用户多样性 Repository"""

    def __init__(self, session):
        super().__init__(session, UserDiversity)

    async def get_or_create(
        self,
        group_id: str,
        user_id: str
    ) -> UserDiversity:
        """
        获取或创建用户多样性记录

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            UserDiversity: 多样性对象
        """
        diversity = await self.find_one(group_id=group_id, user_id=user_id)

        if not diversity:
            diversity = await self.create(
                group_id=group_id,
                user_id=user_id,
                topic_diversity=0.5,
                emotion_diversity=0.5,
                last_topics="[]",
                last_emotions="[]",
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

        return diversity

    async def update_diversity(
        self,
        group_id: str,
        user_id: str,
        topic_diversity: float = None,
        emotion_diversity: float = None,
        last_topics: str = None,
        last_emotions: str = None
    ) -> Optional[UserDiversity]:
        """
        更新多样性数据

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            topic_diversity: 话题多样性
            emotion_diversity: 情感多样性
            last_topics: 最近话题 JSON
            last_emotions: 最近情感 JSON

        Returns:
            Optional[UserDiversity]: 更新后的多样性对象
        """
        diversity = await self.get_or_create(group_id, user_id)

        if topic_diversity is not None:
            diversity.topic_diversity = topic_diversity
        if emotion_diversity is not None:
            diversity.emotion_diversity = emotion_diversity
        if last_topics is not None:
            diversity.last_topics = last_topics
        if last_emotions is not None:
            diversity.last_emotions = last_emotions

        diversity.updated_at = int(time.time())

        return await self.update(diversity)
