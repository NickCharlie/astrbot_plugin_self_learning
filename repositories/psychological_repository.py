"""
心理状态系统相关的 Repository
"""
import time
from sqlalchemy import select, and_
from typing import Optional, List
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import (
    CompositePsychologicalState,
    PsychologicalStateComponent,
    PsychologicalStateHistory
)


class PsychologicalStateRepository(BaseRepository[CompositePsychologicalState]):
    """复合心理状态 Repository"""

    def __init__(self, session):
        super().__init__(session, CompositePsychologicalState)

    async def get_or_create(
        self,
        group_id: str,
        user_id: str
    ) -> CompositePsychologicalState:
        """
        获取或创建心理状态

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            CompositePsychologicalState: 心理状态对象
        """
        state = await self.find_one(group_id=group_id, user_id=user_id)

        if not state:
            state = await self.create(
                group_id=group_id,
                user_id=user_id,
                overall_state="neutral",
                state_intensity=0.5,
                last_transition_time=int(time.time()),
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

        return state

    async def update_state(
        self,
        group_id: str,
        user_id: str,
        overall_state: str = None,
        state_intensity: float = None
    ) -> Optional[CompositePsychologicalState]:
        """
        更新心理状态

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            overall_state: 总体状态
            state_intensity: 状态强度

        Returns:
            Optional[CompositePsychologicalState]: 更新后的状态
        """
        state = await self.get_or_create(group_id, user_id)

        if overall_state is not None and overall_state != state.overall_state:
            state.overall_state = overall_state
            state.last_transition_time = int(time.time())

        if state_intensity is not None:
            state.state_intensity = state_intensity

        state.updated_at = int(time.time())

        return await self.update(state)


class PsychologicalComponentRepository(BaseRepository[PsychologicalStateComponent]):
    """心理状态组件 Repository"""

    def __init__(self, session):
        super().__init__(session, PsychologicalStateComponent)

    async def get_components(
        self,
        state_id: int
    ) -> List[PsychologicalStateComponent]:
        """
        获取状态的所有组件

        Args:
            state_id: 状态 ID

        Returns:
            List[PsychologicalStateComponent]: 组件列表
        """
        return await self.find_many(state_id=state_id)

    async def update_component(
        self,
        state_id: int,
        component_name: str,
        value: float,
        threshold: float = None
    ) -> Optional[PsychologicalStateComponent]:
        """
        更新组件值

        Args:
            state_id: 状态 ID
            component_name: 组件名称
            value: 组件值
            threshold: 阈值

        Returns:
            Optional[PsychologicalStateComponent]: 组件对象
        """
        component = await self.find_one(
            state_id=state_id,
            component_name=component_name
        )

        if component:
            component.value = value
            if threshold is not None:
                component.threshold = threshold
            component.updated_at = int(time.time())
            return await self.update(component)
        else:
            return await self.create(
                state_id=state_id,
                component_name=component_name,
                value=value,
                threshold=threshold or 0.5,
                created_at=int(time.time()),
                updated_at=int(time.time())
            )


class PsychologicalHistoryRepository(BaseRepository[PsychologicalStateHistory]):
    """心理状态历史 Repository"""

    def __init__(self, session):
        super().__init__(session, PsychologicalStateHistory)

    async def add_history(
        self,
        state_id: int,
        from_state: str,
        to_state: str,
        trigger_event: str = None,
        intensity_change: float = 0.0
    ) -> Optional[PsychologicalStateHistory]:
        """
        添加历史记录

        Args:
            state_id: 状态 ID
            from_state: 起始状态
            to_state: 结束状态
            trigger_event: 触发事件
            intensity_change: 强度变化

        Returns:
            Optional[PsychologicalStateHistory]: 历史记录
        """
        return await self.create(
            state_id=state_id,
            from_state=from_state,
            to_state=to_state,
            trigger_event=trigger_event,
            intensity_change=intensity_change,
            timestamp=int(time.time())
        )

    async def get_recent_history(
        self,
        state_id: int,
        limit: int = 20
    ) -> List[PsychologicalStateHistory]:
        """
        获取最近的历史记录

        Args:
            state_id: 状态 ID
            limit: 返回数量

        Returns:
            List[PsychologicalStateHistory]: 历史记录列表
        """
        try:
            stmt = select(PsychologicalStateHistory).where(
                PsychologicalStateHistory.state_id == state_id
            ).order_by(
                PsychologicalStateHistory.timestamp.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PsychologicalHistoryRepository] 获取历史记录失败: {e}")
            return []

    async def clean_old_history(
        self,
        state_id: int,
        days: int = 30
    ) -> int:
        """
        清理旧历史记录

        Args:
            state_id: 状态 ID
            days: 保留天数

        Returns:
            int: 删除的记录数
        """
        try:
            from sqlalchemy import delete

            cutoff_time = int(time.time()) - (days * 24 * 3600)

            stmt = delete(PsychologicalStateHistory).where(
                and_(
                    PsychologicalStateHistory.state_id == state_id,
                    PsychologicalStateHistory.timestamp < cutoff_time
                )
            )

            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[PsychologicalHistoryRepository] 清理历史记录失败: {e}")
            return 0
