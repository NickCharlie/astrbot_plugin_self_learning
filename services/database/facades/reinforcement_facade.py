"""
强化学习 Facade — 强化学习、人格融合、策略优化的业务入口
"""
import time
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.reinforcement_repository import (
    ReinforcementLearningRepository,
    PersonaFusionRepository,
    StrategyOptimizationRepository,
)


class ReinforcementFacade(BaseFacade):
    """强化学习与策略优化 Facade"""

    async def get_learning_history_for_reinforcement(
        self, group_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取用于强化学习的历史数据"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.performance import LearningPerformanceHistory

                stmt = (
                    select(LearningPerformanceHistory)
                    .where(LearningPerformanceHistory.group_id == group_id)
                    .order_by(desc(LearningPerformanceHistory.timestamp))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'timestamp': row.timestamp,
                        'quality_score': row.quality_score or 0.0,
                        'success': bool(row.success),
                        'successful_pattern': row.successful_pattern or '',
                        'failed_pattern': row.failed_pattern or ''
                    }
                    for row in rows
                ]
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 获取强化学习历史失败: {e}")
            return []

    async def save_reinforcement_learning_result(
        self, group_id: str, result_data: Dict[str, Any]
    ) -> bool:
        """保存强化学习结果"""
        try:
            async with self.get_session() as session:
                repo = ReinforcementLearningRepository(session)
                return await repo.save_reinforcement_result(group_id, result_data)
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 保存强化学习结果失败: {e}")
            return False

    async def get_persona_fusion_history(
        self, group_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取人格融合历史"""
        try:
            async with self.get_session() as session:
                repo = PersonaFusionRepository(session)
                return await repo.get_fusion_history(group_id, limit)
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 获取人格融合历史失败: {e}")
            return []

    async def save_persona_fusion_result(
        self, group_id: str, fusion_data: Dict[str, Any]
    ) -> bool:
        """保存人格融合结果"""
        try:
            async with self.get_session() as session:
                repo = PersonaFusionRepository(session)
                return await repo.save_fusion_result(group_id, fusion_data)
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 保存人格融合结果失败: {e}")
            return False

    async def get_learning_performance_history(
        self, group_id: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """获取学习性能历史"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.performance import LearningPerformanceHistory

                stmt = (
                    select(LearningPerformanceHistory)
                    .where(LearningPerformanceHistory.group_id == group_id)
                    .order_by(desc(LearningPerformanceHistory.timestamp))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'session_id': row.session_id,
                        'timestamp': row.timestamp,
                        'quality_score': row.quality_score or 0.0,
                        'learning_time': row.learning_time or 0.0,
                        'success': bool(row.success)
                    }
                    for row in rows
                ]
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 获取学习性能历史失败: {e}")
            return []

    async def save_strategy_optimization_result(
        self, group_id: str, optimization_data: Dict[str, Any]
    ) -> bool:
        """保存策略优化结果"""
        try:
            async with self.get_session() as session:
                repo = StrategyOptimizationRepository(session)
                return await repo.save_optimization_result(group_id, optimization_data)
        except Exception as e:
            self._logger.error(f"[ReinforcementFacade] 保存策略优化结果失败: {e}")
            return False
