"""Persistence operations for shadow-mode profiles."""

from typing import List, Optional

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ..models.orm.shadow import ShadowProfile
except ImportError:
    from models.orm.shadow import ShadowProfile


class ShadowProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_profiles(self) -> List[ShadowProfile]:
        result = await self.session.execute(
            select(ShadowProfile).order_by(desc(ShadowProfile.updated_at))
        )
        return list(result.scalars().all())

    async def get(self, profile_id: int) -> Optional[ShadowProfile]:
        return await self.session.get(ShadowProfile, profile_id)

    async def get_active(self, target_group_id: str) -> Optional[ShadowProfile]:
        result = await self.session.execute(
            select(ShadowProfile)
            .where(
                ShadowProfile.target_group_id == target_group_id,
                ShadowProfile.enabled.is_(True),
            )
            .order_by(desc(ShadowProfile.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_source_profile(
        self,
        *,
        target_group_id: str,
        source_type: str,
        source_group_id: str,
        sender_id: str,
    ) -> Optional[ShadowProfile]:
        result = await self.session.execute(
            select(ShadowProfile)
            .where(
                ShadowProfile.target_group_id == target_group_id,
                ShadowProfile.source_type == source_type,
                ShadowProfile.source_group_id == source_group_id,
                ShadowProfile.sender_id == sender_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def disable_for_group(
        self, target_group_id: str, *, except_id: Optional[int] = None
    ) -> None:
        stmt = (
            update(ShadowProfile)
            .where(ShadowProfile.target_group_id == target_group_id)
            .values(enabled=False)
        )
        if except_id is not None:
            stmt = stmt.where(ShadowProfile.id != except_id)
        await self.session.execute(stmt)
