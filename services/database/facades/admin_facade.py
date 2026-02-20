"""
管理操作 Facade — 批量清理、导出等管理功能的业务入口
"""
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade


class AdminFacade(BaseFacade):
    """管理操作 Facade"""

    async def clear_all_messages_data(self) -> bool:
        """清除所有消息与学习数据（批量删除多个表）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import delete as sa_delete
                from ....models.orm.message import RawMessage, FilteredMessage
                from ....models.orm.learning import LearningBatch
                from ....models.orm.reinforcement import (
                    ReinforcementLearningResult, PersonaFusionHistory,
                    StrategyOptimizationResult
                )
                from ....models.orm.performance import LearningPerformanceHistory

                tables = [
                    FilteredMessage, RawMessage, LearningBatch,
                    ReinforcementLearningResult, PersonaFusionHistory,
                    StrategyOptimizationResult, LearningPerformanceHistory,
                ]
                for table in tables:
                    try:
                        await session.execute(sa_delete(table))
                    except Exception as table_err:
                        self._logger.warning(
                            f"[AdminFacade] 清除 {table.__tablename__} 失败: {table_err}"
                        )

                await session.commit()
                self._logger.info("[AdminFacade] 所有消息与学习数据已清除")
                return True
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除数据失败: {e}")
            return False

    async def export_messages_learning_data(
        self, group_id: str = None
    ) -> Dict[str, Any]:
        """导出原始消息和筛选消息"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.message import RawMessage, FilteredMessage

                raw_stmt = select(RawMessage)
                filtered_stmt = select(FilteredMessage)
                if group_id:
                    raw_stmt = raw_stmt.where(RawMessage.group_id == group_id)
                    filtered_stmt = filtered_stmt.where(FilteredMessage.group_id == group_id)

                raw_result = await session.execute(raw_stmt)
                raw_msgs = raw_result.scalars().all()

                filtered_result = await session.execute(filtered_stmt)
                filtered_msgs = filtered_result.scalars().all()

                return {
                    'raw_messages': [
                        {
                            'id': m.id, 'sender_id': m.sender_id,
                            'message': m.message, 'group_id': m.group_id,
                            'timestamp': m.timestamp,
                        }
                        for m in raw_msgs
                    ],
                    'filtered_messages': [
                        {
                            'id': m.id, 'message': m.message,
                            'group_id': m.group_id, 'confidence': m.confidence,
                            'timestamp': m.timestamp,
                        }
                        for m in filtered_msgs
                    ],
                }
        except Exception as e:
            self._logger.error(f"[AdminFacade] 导出数据失败: {e}")
            return {'raw_messages': [], 'filtered_messages': []}
