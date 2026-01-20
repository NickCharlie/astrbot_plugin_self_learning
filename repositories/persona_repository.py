"""
人格系统相关的 Repository
提供人格多样性、属性权重、演化快照的数据访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from typing import List, Optional, Dict, Any
from astrbot.api import logger
import time

from .base_repository import BaseRepository
from ..models.orm import (
    PersonaDiversityScore,
    PersonaAttributeWeight,
    PersonaEvolutionSnapshot
)


class PersonaDiversityScoreRepository(BaseRepository[PersonaDiversityScore]):
    """人格多样性评分 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PersonaDiversityScore)

    async def save_diversity_score(
        self,
        group_id: str,
        persona_id: str,
        diversity_dimension: str,
        score: float,
        calculated_at: Optional[float] = None
    ) -> Optional[PersonaDiversityScore]:
        """
        保存人格多样性评分

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            diversity_dimension: 多样性维度 (emotion, topic, style, etc.)
            score: 多样性分数 (0-1)
            calculated_at: 计算时间戳

        Returns:
            Optional[PersonaDiversityScore]: 创建的评分记录
        """
        try:
            if calculated_at is None:
                calculated_at = time.time()

            return await self.create(
                group_id=group_id,
                persona_id=persona_id,
                diversity_dimension=diversity_dimension,
                score=score,
                calculated_at=calculated_at
            )
        except Exception as e:
            logger.error(f"[PersonaDiversityScoreRepository] 保存多样性评分失败: {e}")
            return None

    async def get_diversity_scores(
        self,
        group_id: str,
        persona_id: str,
        diversity_dimension: Optional[str] = None,
        limit: int = 50
    ) -> List[PersonaDiversityScore]:
        """
        获取人格多样性评分列表

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            diversity_dimension: 多样性维度过滤（可选）
            limit: 最大返回数量

        Returns:
            List[PersonaDiversityScore]: 评分列表
        """
        try:
            stmt = select(PersonaDiversityScore).where(
                and_(
                    PersonaDiversityScore.group_id == group_id,
                    PersonaDiversityScore.persona_id == persona_id
                )
            )

            if diversity_dimension:
                stmt = stmt.where(PersonaDiversityScore.diversity_dimension == diversity_dimension)

            stmt = stmt.order_by(
                desc(PersonaDiversityScore.calculated_at)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PersonaDiversityScoreRepository] 获取多样性评分列表失败: {e}")
            return []

    async def get_latest_scores_by_dimension(
        self,
        group_id: str,
        persona_id: str
    ) -> Dict[str, float]:
        """
        获取各维度的最新多样性评分

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID

        Returns:
            Dict[str, float]: {维度名: 最新分数}
        """
        try:
            # 获取每个维度的最新评分
            stmt = select(
                PersonaDiversityScore.diversity_dimension,
                PersonaDiversityScore.score,
                PersonaDiversityScore.calculated_at
            ).where(
                and_(
                    PersonaDiversityScore.group_id == group_id,
                    PersonaDiversityScore.persona_id == persona_id
                )
            ).order_by(desc(PersonaDiversityScore.calculated_at))

            result = await self.session.execute(stmt)
            rows = result.fetchall()

            # 按维度去重，保留最新的
            dimension_scores = {}
            for dimension, score, _ in rows:
                if dimension not in dimension_scores:
                    dimension_scores[dimension] = score

            return dimension_scores

        except Exception as e:
            logger.error(f"[PersonaDiversityScoreRepository] 获取最新维度评分失败: {e}")
            return {}


class PersonaAttributeWeightRepository(BaseRepository[PersonaAttributeWeight]):
    """人格属性权重 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PersonaAttributeWeight)

    async def save_attribute_weight(
        self,
        group_id: str,
        persona_id: str,
        attribute_name: str,
        weight: float,
        adjustment_reason: Optional[str] = None,
        updated_at: Optional[float] = None
    ) -> Optional[PersonaAttributeWeight]:
        """
        保存人格属性权重

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            attribute_name: 属性名称
            weight: 权重值 (0-1)
            adjustment_reason: 调整原因
            updated_at: 更新时间戳

        Returns:
            Optional[PersonaAttributeWeight]: 创建的权重记录
        """
        try:
            if updated_at is None:
                updated_at = time.time()

            return await self.create(
                group_id=group_id,
                persona_id=persona_id,
                attribute_name=attribute_name,
                weight=weight,
                adjustment_reason=adjustment_reason,
                updated_at=updated_at
            )
        except Exception as e:
            logger.error(f"[PersonaAttributeWeightRepository] 保存属性权重失败: {e}")
            return None

    async def get_attribute_weights(
        self,
        group_id: str,
        persona_id: str,
        attribute_name: Optional[str] = None,
        limit: int = 50
    ) -> List[PersonaAttributeWeight]:
        """
        获取人格属性权重列表

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            attribute_name: 属性名称过滤（可选）
            limit: 最大返回数量

        Returns:
            List[PersonaAttributeWeight]: 权重列表
        """
        try:
            stmt = select(PersonaAttributeWeight).where(
                and_(
                    PersonaAttributeWeight.group_id == group_id,
                    PersonaAttributeWeight.persona_id == persona_id
                )
            )

            if attribute_name:
                stmt = stmt.where(PersonaAttributeWeight.attribute_name == attribute_name)

            stmt = stmt.order_by(
                desc(PersonaAttributeWeight.updated_at)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PersonaAttributeWeightRepository] 获取属性权重列表失败: {e}")
            return []

    async def get_latest_weights(
        self,
        group_id: str,
        persona_id: str
    ) -> Dict[str, float]:
        """
        获取各属性的最新权重

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID

        Returns:
            Dict[str, float]: {属性名: 最新权重}
        """
        try:
            stmt = select(
                PersonaAttributeWeight.attribute_name,
                PersonaAttributeWeight.weight,
                PersonaAttributeWeight.updated_at
            ).where(
                and_(
                    PersonaAttributeWeight.group_id == group_id,
                    PersonaAttributeWeight.persona_id == persona_id
                )
            ).order_by(desc(PersonaAttributeWeight.updated_at))

            result = await self.session.execute(stmt)
            rows = result.fetchall()

            # 按属性名去重，保留最新的
            attribute_weights = {}
            for attr_name, weight, _ in rows:
                if attr_name not in attribute_weights:
                    attribute_weights[attr_name] = weight

            return attribute_weights

        except Exception as e:
            logger.error(f"[PersonaAttributeWeightRepository] 获取最新属性权重失败: {e}")
            return {}

    async def update_attribute_weight(
        self,
        group_id: str,
        persona_id: str,
        attribute_name: str,
        new_weight: float,
        adjustment_reason: Optional[str] = None
    ) -> bool:
        """
        更新属性权重（通过插入新记录）

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            attribute_name: 属性名称
            new_weight: 新权重值
            adjustment_reason: 调整原因

        Returns:
            bool: 是否成功
        """
        try:
            weight_record = await self.save_attribute_weight(
                group_id=group_id,
                persona_id=persona_id,
                attribute_name=attribute_name,
                weight=new_weight,
                adjustment_reason=adjustment_reason
            )
            return weight_record is not None

        except Exception as e:
            logger.error(f"[PersonaAttributeWeightRepository] 更新属性权重失败: {e}")
            return False


class PersonaEvolutionSnapshotRepository(BaseRepository[PersonaEvolutionSnapshot]):
    """人格演化快照 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PersonaEvolutionSnapshot)

    async def save_evolution_snapshot(
        self,
        group_id: str,
        persona_id: str,
        snapshot_data: str,
        version: int,
        snapshot_timestamp: Optional[float] = None,
        trigger_event: Optional[str] = None
    ) -> Optional[PersonaEvolutionSnapshot]:
        """
        保存人格演化快照

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            snapshot_data: 快照数据（JSON字符串）
            version: 版本号
            snapshot_timestamp: 快照时间戳
            trigger_event: 触发事件描述

        Returns:
            Optional[PersonaEvolutionSnapshot]: 创建的快照记录
        """
        try:
            if snapshot_timestamp is None:
                snapshot_timestamp = time.time()

            return await self.create(
                group_id=group_id,
                persona_id=persona_id,
                snapshot_data=snapshot_data,
                version=version,
                snapshot_timestamp=snapshot_timestamp,
                trigger_event=trigger_event
            )
        except Exception as e:
            logger.error(f"[PersonaEvolutionSnapshotRepository] 保存演化快照失败: {e}")
            return None

    async def get_evolution_snapshots(
        self,
        group_id: str,
        persona_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 50
    ) -> List[PersonaEvolutionSnapshot]:
        """
        获取人格演化快照列表

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            start_time: 开始时间戳（可选）
            end_time: 结束时间戳（可选）
            limit: 最大返回数量

        Returns:
            List[PersonaEvolutionSnapshot]: 快照列表
        """
        try:
            stmt = select(PersonaEvolutionSnapshot).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id
                )
            )

            if start_time is not None:
                stmt = stmt.where(PersonaEvolutionSnapshot.snapshot_timestamp >= start_time)
            if end_time is not None:
                stmt = stmt.where(PersonaEvolutionSnapshot.snapshot_timestamp <= end_time)

            stmt = stmt.order_by(
                desc(PersonaEvolutionSnapshot.snapshot_timestamp)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[PersonaEvolutionSnapshotRepository] 获取演化快照列表失败: {e}")
            return []

    async def get_snapshot_by_version(
        self,
        group_id: str,
        persona_id: str,
        version: int
    ) -> Optional[PersonaEvolutionSnapshot]:
        """
        根据版本号获取快照

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID
            version: 版本号

        Returns:
            Optional[PersonaEvolutionSnapshot]: 快照记录
        """
        try:
            stmt = select(PersonaEvolutionSnapshot).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id,
                    PersonaEvolutionSnapshot.version == version
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[PersonaEvolutionSnapshotRepository] 根据版本获取快照失败: {e}")
            return None

    async def get_latest_snapshot(
        self,
        group_id: str,
        persona_id: str
    ) -> Optional[PersonaEvolutionSnapshot]:
        """
        获取最新的演化快照

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID

        Returns:
            Optional[PersonaEvolutionSnapshot]: 最新快照
        """
        try:
            stmt = select(PersonaEvolutionSnapshot).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id
                )
            ).order_by(
                desc(PersonaEvolutionSnapshot.version)
            ).limit(1)

            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[PersonaEvolutionSnapshotRepository] 获取最新快照失败: {e}")
            return None

    async def get_version_statistics(
        self,
        group_id: str,
        persona_id: str
    ) -> Dict[str, Any]:
        """
        获取版本统计信息

        Args:
            group_id: 群组 ID
            persona_id: 人格 ID

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总快照数
            total_stmt = select(func.count()).select_from(PersonaEvolutionSnapshot).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id
                )
            )
            total_result = await self.session.execute(total_stmt)
            total_snapshots = total_result.scalar() or 0

            # 最新版本号
            max_version_stmt = select(func.max(PersonaEvolutionSnapshot.version)).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id
                )
            )
            max_version_result = await self.session.execute(max_version_stmt)
            latest_version = max_version_result.scalar() or 0

            # 最早和最晚时间戳
            time_range_stmt = select(
                func.min(PersonaEvolutionSnapshot.snapshot_timestamp).label('earliest'),
                func.max(PersonaEvolutionSnapshot.snapshot_timestamp).label('latest')
            ).where(
                and_(
                    PersonaEvolutionSnapshot.group_id == group_id,
                    PersonaEvolutionSnapshot.persona_id == persona_id
                )
            )
            time_range_result = await self.session.execute(time_range_stmt)
            time_range = time_range_result.fetchone()

            return {
                'total_snapshots': total_snapshots,
                'latest_version': latest_version,
                'earliest_timestamp': time_range[0] if time_range else None,
                'latest_timestamp': time_range[1] if time_range else None
            }

        except Exception as e:
            logger.error(f"[PersonaEvolutionSnapshotRepository] 获取版本统计失败: {e}")
            return {
                'total_snapshots': 0,
                'latest_version': 0,
                'earliest_timestamp': None,
                'latest_timestamp': None
            }
