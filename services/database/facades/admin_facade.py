"""
管理操作 Facade — 批量清理、导出等管理功能的业务入口
"""
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from sqlalchemy import delete as sa_delete, select, func
from ....models.orm.learning import (
    LearningBatch, PersonaLearningReview, StyleLearningReview,
    StyleLearningPattern, LearningSession, LearningReinforcementFeedback,
    LearningOptimizationLog,
)
from ....models.orm.message import (
    FilteredMessage, RawMessage, BotMessage,
    ConversationContext, ConversationTopicClustering,
    ConversationQualityMetrics, ContextSimilarityCache,
)
from ....models.orm.expression import (
    ExpressionPattern, ExpressionGenerationResult,
    AdaptiveResponseTemplate, StyleProfile,
    StyleLearningRecord, LanguageStylePattern,
)
from ....models.orm.jargon import Jargon, JargonUsageFrequency
from ....models.orm.performance import LearningPerformanceHistory
from ....models.orm.reinforcement import (
    PersonaFusionHistory, ReinforcementLearningResult, StrategyOptimizationResult,
)
from ....models.orm.psychological import PersonaBackup


class AdminFacade(BaseFacade):
    """管理操作 Facade"""

    # ── helpers ──────────────────────────────────────────────

    async def _bulk_delete(self, session, tables: list) -> int:
        """Delete all rows from *tables*, return total deleted count."""
        total = 0
        for table in tables:
            try:
                result = await session.execute(sa_delete(table))
                total += result.rowcount or 0
            except Exception as table_err:
                self._logger.warning(
                    f"[AdminFacade] 清除 {table.__tablename__} 失败: {table_err}"
                )
        return total

    async def _count_tables(self, session, tables: list) -> int:
        """Count total rows across *tables*."""
        total = 0
        for table in tables:
            try:
                result = await session.execute(
                    select(func.count()).select_from(table)
                )
                total += result.scalar() or 0
            except Exception:
                pass
        return total

    # ── clear: messages ──────────────────────────────────────

    async def clear_all_messages_data(self) -> bool:
        """清除所有消息与学习数据（批量删除多个表）"""
        try:
            async with self.get_session() as session:

                tables = [
                    FilteredMessage, RawMessage, LearningBatch,
                    ReinforcementLearningResult, PersonaFusionHistory,
                    StrategyOptimizationResult, LearningPerformanceHistory,
                ]
                await self._bulk_delete(session, tables)
                await session.commit()
                self._logger.info("[AdminFacade] 所有消息与学习数据已清除")
                return True
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除数据失败: {e}")
            return False

    _MESSAGE_TABLES = [
        RawMessage, FilteredMessage, BotMessage,
        ConversationContext, ConversationTopicClustering,
        ConversationQualityMetrics, ContextSimilarityCache,
    ]

    async def clear_messages_data(self) -> Dict[str, Any]:
        """清除所有消息数据（原始/筛选/Bot/对话上下文等）"""
        try:
            async with self.get_session() as session:
                deleted = await self._bulk_delete(session, self._MESSAGE_TABLES)
                await session.commit()
                self._logger.info(f"[AdminFacade] 消息数据已清除，共 {deleted} 行")
                return {'success': True, 'deleted': deleted}
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除消息数据失败: {e}")
            return {'success': False, 'deleted': 0}

    async def count_messages_data(self) -> int:
        """统计所有消息数据行数"""
        try:
            async with self.get_session() as session:
                return await self._count_tables(session, self._MESSAGE_TABLES)
        except Exception:
            return 0

    # ── clear: persona reviews ───────────────────────────────

    _PERSONA_REVIEW_TABLES = [PersonaLearningReview, PersonaBackup]

    async def clear_persona_reviews_data(self) -> Dict[str, Any]:
        """清除所有人格审查数据"""
        try:
            async with self.get_session() as session:
                deleted = await self._bulk_delete(session, self._PERSONA_REVIEW_TABLES)
                await session.commit()
                self._logger.info(f"[AdminFacade] 人格审查数据已清除，共 {deleted} 行")
                return {'success': True, 'deleted': deleted}
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除人格审查数据失败: {e}")
            return {'success': False, 'deleted': 0}

    async def count_persona_reviews_data(self) -> int:
        """统计所有人格审查数据行数"""
        try:
            async with self.get_session() as session:
                return await self._count_tables(session, self._PERSONA_REVIEW_TABLES)
        except Exception:
            return 0

    # ── clear: style learning ────────────────────────────────

    _STYLE_LEARNING_TABLES = [
        StyleLearningReview, StyleLearningPattern,
        ExpressionPattern, ExpressionGenerationResult,
        AdaptiveResponseTemplate, StyleProfile,
        StyleLearningRecord, LanguageStylePattern,
    ]

    async def clear_style_learning_data(self) -> Dict[str, Any]:
        """清除所有对话风格学习数据"""
        try:
            async with self.get_session() as session:
                deleted = await self._bulk_delete(session, self._STYLE_LEARNING_TABLES)
                await session.commit()
                self._logger.info(f"[AdminFacade] 风格学习数据已清除，共 {deleted} 行")
                return {'success': True, 'deleted': deleted}
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除风格学习数据失败: {e}")
            return {'success': False, 'deleted': 0}

    async def count_style_learning_data(self) -> int:
        """统计所有风格学习数据行数"""
        try:
            async with self.get_session() as session:
                return await self._count_tables(session, self._STYLE_LEARNING_TABLES)
        except Exception:
            return 0

    # ── clear: jargon ────────────────────────────────────────

    _JARGON_TABLES = [JargonUsageFrequency, Jargon]

    async def clear_jargon_data(self) -> Dict[str, Any]:
        """清除所有黑话数据"""
        try:
            async with self.get_session() as session:
                # JargonUsageFrequency has FK to Jargon — delete child first
                deleted = await self._bulk_delete(session, self._JARGON_TABLES)
                await session.commit()
                self._logger.info(f"[AdminFacade] 黑话数据已清除，共 {deleted} 行")
                return {'success': True, 'deleted': deleted}
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除黑话数据失败: {e}")
            return {'success': False, 'deleted': 0}

    async def count_jargon_data(self) -> int:
        """统计所有黑话数据行数"""
        try:
            async with self.get_session() as session:
                return await self._count_tables(session, self._JARGON_TABLES)
        except Exception:
            return 0

    # ── clear: learning history ──────────────────────────────

    _LEARNING_HISTORY_TABLES = [
        LearningBatch, LearningSession,
        LearningReinforcementFeedback, LearningOptimizationLog,
        LearningPerformanceHistory,
        ReinforcementLearningResult, PersonaFusionHistory,
        StrategyOptimizationResult,
    ]

    async def clear_learning_history_data(self) -> Dict[str, Any]:
        """清除所有学习历史数据（批次/会话/强化/优化等）"""
        try:
            async with self.get_session() as session:
                deleted = await self._bulk_delete(session, self._LEARNING_HISTORY_TABLES)
                await session.commit()
                self._logger.info(f"[AdminFacade] 学习历史数据已清除，共 {deleted} 行")
                return {'success': True, 'deleted': deleted}
        except Exception as e:
            self._logger.error(f"[AdminFacade] 清除学习历史数据失败: {e}")
            return {'success': False, 'deleted': 0}

    async def count_learning_history_data(self) -> int:
        """统计所有学习历史数据行数"""
        try:
            async with self.get_session() as session:
                return await self._count_tables(session, self._LEARNING_HISTORY_TABLES)
        except Exception:
            return 0

    # ── clear: all data ──────────────────────────────────────

    async def clear_all_plugin_data(self) -> Dict[str, Any]:
        """一键清空所有插件数据"""
        results = {}
        total_deleted = 0
        all_success = True

        for name, method in [
            ('messages', self.clear_messages_data),
            ('persona_reviews', self.clear_persona_reviews_data),
            ('style_learning', self.clear_style_learning_data),
            ('jargon', self.clear_jargon_data),
            ('learning_history', self.clear_learning_history_data),
        ]:
            r = await method()
            results[name] = r
            total_deleted += r.get('deleted', 0)
            if not r.get('success'):
                all_success = False

        self._logger.info(
            f"[AdminFacade] 全部数据清除完成，共 {total_deleted} 行，"
            f"{'全部成功' if all_success else '部分失败'}"
        )
        return {
            'success': all_success,
            'deleted': total_deleted,
            'details': results,
        }

    async def get_data_statistics(self) -> Dict[str, int]:
        """获取各类数据的统计行数"""
        return {
            'messages': await self.count_messages_data(),
            'persona_reviews': await self.count_persona_reviews_data(),
            'style_learning': await self.count_style_learning_data(),
            'jargon': await self.count_jargon_data(),
            'learning_history': await self.count_learning_history_data(),
        }

    async def export_messages_learning_data(
        self, group_id: str = None
    ) -> Dict[str, Any]:
        """导出原始消息和筛选消息"""
        try:
            async with self.get_session() as session:

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
