"""强化学习相关的Repository层"""
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from astrbot.api import logger

from ..models.orm.reinforcement import (
    ReinforcementLearningResult,
    PersonaFusionHistory,
    StrategyOptimizationResult
)


class ReinforcementLearningRepository:
    """强化学习结果Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_reinforcement_result(
        self,
        group_id: str,
        result_data: Dict[str, Any]
    ) -> bool:
        """
        保存强化学习结果

        Args:
            group_id: 群组ID
            result_data: 结果数据字典

        Returns:
            是否成功
        """
        try:
            result = ReinforcementLearningResult(
                group_id=group_id,
                timestamp=result_data.get('timestamp', time.time()),
                replay_analysis=result_data.get('replay_analysis'),
                optimization_strategy=result_data.get('optimization_strategy'),
                reinforcement_feedback=result_data.get('reinforcement_feedback'),
                next_action=result_data.get('next_action')
            )

            self.session.add(result)
            await self.session.commit()

            logger.info(f"✅ 保存强化学习结果成功 (group: {group_id})")
            return True

        except Exception as e:
            logger.error(f"❌ 保存强化学习结果失败: {e}", exc_info=True)
            await self.session.rollback()
            return False

    async def get_recent_results(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取最近的强化学习结果

        Args:
            group_id: 群组ID
            limit: 限制数量

        Returns:
            结果列表
        """
        try:
            stmt = (
                select(ReinforcementLearningResult)
                .where(ReinforcementLearningResult.group_id == group_id)
                .order_by(desc(ReinforcementLearningResult.timestamp))
                .limit(limit)
            )

            result = await self.session.execute(stmt)
            results = result.scalars().all()

            return [r.to_dict() for r in results]

        except Exception as e:
            logger.error(f"❌ 获取强化学习结果失败: {e}", exc_info=True)
            return []


class PersonaFusionRepository:
    """人格融合历史Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_fusion_result(
        self,
        group_id: str,
        fusion_data: Dict[str, Any]
    ) -> bool:
        """
        保存人格融合结果

        Args:
            group_id: 群组ID
            fusion_data: 融合数据字典

        Returns:
            是否成功
        """
        try:
            fusion = PersonaFusionHistory(
                group_id=group_id,
                timestamp=fusion_data.get('timestamp', time.time()),
                base_persona_hash=fusion_data.get('base_persona_hash'),
                incremental_hash=fusion_data.get('incremental_hash'),
                fusion_result=fusion_data.get('fusion_result'),
                compatibility_score=fusion_data.get('compatibility_score')
            )

            self.session.add(fusion)
            await self.session.commit()

            logger.info(f"✅ 保存人格融合结果成功 (group: {group_id})")
            return True

        except Exception as e:
            logger.error(f"❌ 保存人格融合结果失败: {e}", exc_info=True)
            await self.session.rollback()
            return False

    async def get_fusion_history(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取人格融合历史

        Args:
            group_id: 群组ID
            limit: 限制数量

        Returns:
            历史记录列表
        """
        try:
            stmt = (
                select(PersonaFusionHistory)
                .where(PersonaFusionHistory.group_id == group_id)
                .order_by(desc(PersonaFusionHistory.timestamp))
                .limit(limit)
            )

            result = await self.session.execute(stmt)
            histories = result.scalars().all()

            return [h.to_dict() for h in histories]

        except Exception as e:
            logger.error(f"❌ 获取人格融合历史失败: {e}", exc_info=True)
            return []


class StrategyOptimizationRepository:
    """策略优化结果Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_optimization_result(
        self,
        group_id: str,
        optimization_data: Dict[str, Any]
    ) -> bool:
        """
        保存策略优化结果

        Args:
            group_id: 群组ID
            optimization_data: 优化数据字典

        Returns:
            是否成功
        """
        try:
            result = StrategyOptimizationResult(
                group_id=group_id,
                timestamp=optimization_data.get('timestamp', time.time()),
                strategy_type=optimization_data.get('strategy_type'),
                optimization_details=optimization_data.get('optimization_details'),
                performance_metrics=optimization_data.get('performance_metrics')
            )

            self.session.add(result)
            await self.session.commit()

            logger.info(f"✅ 保存策略优化结果成功 (group: {group_id})")
            return True

        except Exception as e:
            logger.error(f"❌ 保存策略优化结果失败: {e}", exc_info=True)
            await self.session.rollback()
            return False

    async def get_recent_optimizations(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取最近的策略优化结果

        Args:
            group_id: 群组ID
            limit: 限制数量

        Returns:
            结果列表
        """
        try:
            stmt = (
                select(StrategyOptimizationResult)
                .where(StrategyOptimizationResult.group_id == group_id)
                .order_by(desc(StrategyOptimizationResult.timestamp))
                .limit(limit)
            )

            result = await self.session.execute(stmt)
            results = result.scalars().all()

            return [r.to_dict() for r in results]

        except Exception as e:
            logger.error(f"❌ 获取策略优化结果失败: {e}", exc_info=True)
            return []
