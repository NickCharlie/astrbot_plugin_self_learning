"""
时间衰减管理器 - 实现MaiBot的时间衰减机制（ORM 版本）
为现有学习系统添加时间衰减功能，保持学习内容的时效性

注意：expression_patterns 的衰减由 ExpressionPatternLearner._apply_time_decay 处理，
本模块处理其余表的衰减。
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from astrbot.api import logger

from ...core.interfaces import ServiceLifecycle
from ...config import PluginConfig
from ...exceptions import TimeDecayError
from ..database import DatabaseManager


@dataclass
class DecayConfig:
    """衰减配置"""
    decay_days: int = 15  # MaiBot的15天衰减周期
    decay_min: float = 0.01  # 最小衰减值
    table_key: str = ""  # 逻辑表标识（不再直接用于 SQL）


class TimeDecayManager:
    """
    时间衰减管理器 - 完全基于MaiBot的衰减机制设计（ORM 版本）
    为各种学习数据提供统一的时间衰减管理

    所有数据库操作通过 SQLAlchemy ORM 执行，不使用原始 SQL。
    """

    def __init__(self, config: PluginConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self._status = ServiceLifecycle.CREATED

        # 预定义的衰减配置（逻辑名 → 衰减参数）
        self.decay_configs = {
            'learning_batches': DecayConfig(
                decay_days=7,
                table_key='learning_batches',
            ),
            'expression_patterns': DecayConfig(
                decay_days=15,
                table_key='expression_patterns',
            ),
        }

    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        logger.info("TimeDecayManager服务已启动")
        return True

    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        logger.info("TimeDecayManager服务已停止")
        return True

    def calculate_decay_factor(self, time_diff_days: float, decay_days: int = 15) -> float:
        """
        计算衰减因子 - 完全采用MaiBot的衰减算法

        Args:
            time_diff_days: 时间差（天）
            decay_days: 衰减周期天数

        Returns:
            衰减因子
        """
        if time_diff_days <= 0:
            return 0.0  # 刚激活的不衰减

        if time_diff_days >= decay_days:
            return 0.01  # 长时间未活跃的大幅衰减

        # 使用二次函数插值：在0-decay_days天之间从0衰减到0.01
        a = 0.01 / (decay_days ** 2)
        decay = a * (time_diff_days ** 2)

        return min(0.01, decay)

    async def apply_decay_to_table(
        self, decay_config: DecayConfig, group_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        对指定表应用时间衰减（ORM 版本）

        Args:
            decay_config: 衰减配置
            group_id: 可选的群组ID筛选

        Returns:
            (更新数量, 删除数量)
        """
        table_key = decay_config.table_key
        handler = self._TABLE_HANDLERS.get(table_key)
        if not handler:
            logger.debug(f"表 {table_key} 没有衰减处理器，跳过")
            return 0, 0

        try:
            return await handler(self, decay_config, group_id)
        except Exception as e:
            logger.error(f"对表 {table_key} 应用时间衰减失败: {e}")
            raise TimeDecayError(f"时间衰减失败: {e}")

    # ---- Per-table decay handlers ----

    async def _decay_learning_batches(
        self, decay_config: DecayConfig, group_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """对 learning_batches 表应用衰减"""
        from sqlalchemy import select, delete
        from ...models.orm.learning import LearningBatch

        current_time = time.time()
        updated_count = 0
        deleted_count = 0

        async with self.db_manager.get_session() as session:
            stmt = select(LearningBatch)
            if group_id:
                stmt = stmt.where(LearningBatch.group_id == group_id)
            result = await session.execute(stmt)
            batches = result.scalars().all()

            ids_to_delete = []
            for batch in batches:
                if batch.start_time is None:
                    continue
                time_diff_days = (current_time - batch.start_time) / (24 * 3600)
                decay_value = self.calculate_decay_factor(time_diff_days, decay_config.decay_days)

                current_score = batch.quality_score or 1.0
                new_score = max(decay_config.decay_min, current_score - decay_value)

                if new_score <= decay_config.decay_min:
                    ids_to_delete.append(batch.id)
                    deleted_count += 1
                else:
                    batch.quality_score = new_score
                    updated_count += 1

            if ids_to_delete:
                await session.execute(
                    delete(LearningBatch).where(LearningBatch.id.in_(ids_to_delete))
                )

            await session.commit()

        if updated_count > 0 or deleted_count > 0:
            group_info = f" (群组: {group_id})" if group_id else ""
            logger.info(f"表 learning_batches{group_info} 时间衰减完成：更新 {updated_count}，删除 {deleted_count}")

        return updated_count, deleted_count

    async def _decay_expression_patterns(
        self, decay_config: DecayConfig, group_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """对 expression_patterns 表应用衰减"""
        from sqlalchemy import select, delete
        from ...models.orm.expression import ExpressionPattern

        current_time = time.time()
        updated_count = 0
        deleted_count = 0

        async with self.db_manager.get_session() as session:
            stmt = select(ExpressionPattern)
            if group_id:
                stmt = stmt.where(ExpressionPattern.group_id == group_id)
            result = await session.execute(stmt)
            patterns = result.scalars().all()

            ids_to_delete = []
            for pattern in patterns:
                time_diff_days = (current_time - pattern.last_active_time) / (24 * 3600)
                decay_value = self.calculate_decay_factor(time_diff_days, decay_config.decay_days)
                new_weight = max(decay_config.decay_min, pattern.weight - decay_value)

                if new_weight <= decay_config.decay_min:
                    ids_to_delete.append(pattern.id)
                    deleted_count += 1
                else:
                    pattern.weight = new_weight
                    updated_count += 1

            if ids_to_delete:
                await session.execute(
                    delete(ExpressionPattern).where(ExpressionPattern.id.in_(ids_to_delete))
                )

            await session.commit()

        if updated_count > 0 or deleted_count > 0:
            group_info = f" (群组: {group_id})" if group_id else ""
            logger.info(f"表 expression_patterns{group_info} 时间衰减完成：更新 {updated_count}，删除 {deleted_count}")

        return updated_count, deleted_count

    # Handler registry
    _TABLE_HANDLERS = {
        'learning_batches': _decay_learning_batches,
        'expression_patterns': _decay_expression_patterns,
    }

    async def apply_decay_to_all_tables(
        self, group_id: Optional[str] = None
    ) -> Dict[str, Tuple[int, int]]:
        """
        对所有配置的表应用时间衰减

        Args:
            group_id: 可选的群组ID筛选

        Returns:
            每个表的(更新数量, 删除数量)结果
        """
        results = {}

        for table_name, decay_config in self.decay_configs.items():
            try:
                updated, deleted = await self.apply_decay_to_table(decay_config, group_id)
                results[table_name] = (updated, deleted)
            except Exception as e:
                logger.error(f"对表 {table_name} 应用衰减失败: {e}")
                results[table_name] = (0, 0)

        return results

    async def add_decay_config(self, name: str, config: DecayConfig):
        """添加新的衰减配置"""
        self.decay_configs[name] = config
        logger.info(f"添加衰减配置: {name}")

    async def get_decay_statistics(
        self, group_id: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取衰减统计信息（ORM 版本）

        Args:
            group_id: 可选的群组ID筛选

        Returns:
            各表的衰减统计信息
        """
        statistics = {}
        current_time = time.time()

        # learning_batches 统计
        try:
            stats = await self._stats_learning_batches(group_id, current_time)
            if stats:
                statistics['learning_batches'] = stats
        except Exception as e:
            logger.error(f"获取 learning_batches 衰减统计失败: {e}")
            statistics['learning_batches'] = {'error': str(e)}

        # expression_patterns 统计
        try:
            stats = await self._stats_expression_patterns(group_id, current_time)
            if stats:
                statistics['expression_patterns'] = stats
        except Exception as e:
            logger.error(f"获取 expression_patterns 衰减统计失败: {e}")
            statistics['expression_patterns'] = {'error': str(e)}

        return statistics

    async def _stats_learning_batches(
        self, group_id: Optional[str], current_time: float
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy import select, func
        from ...models.orm.learning import LearningBatch

        async with self.db_manager.get_session() as session:
            stmt = select(
                func.count().label('total_count'),
                func.avg(LearningBatch.quality_score).label('avg_weight'),
                func.min(LearningBatch.start_time).label('oldest_time'),
                func.max(LearningBatch.start_time).label('newest_time'),
            ).select_from(LearningBatch)
            if group_id:
                stmt = stmt.where(LearningBatch.group_id == group_id)

            row = (await session.execute(stmt)).one_or_none()
            if not row or not row.total_count:
                return None

            cfg = self.decay_configs.get('learning_batches', DecayConfig(decay_days=7))
            oldest_days = (current_time - row.oldest_time) / (24 * 3600) if row.oldest_time else 0
            newest_days = (current_time - row.newest_time) / (24 * 3600) if row.newest_time else 0

            return {
                'total_count': row.total_count,
                'avg_weight': round(row.avg_weight, 3) if row.avg_weight else 0,
                'oldest_days': round(oldest_days, 1),
                'newest_days': round(newest_days, 1),
                'decay_config': {'decay_days': cfg.decay_days, 'decay_min': cfg.decay_min},
            }

    async def _stats_expression_patterns(
        self, group_id: Optional[str], current_time: float
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy import select, func
        from ...models.orm.expression import ExpressionPattern

        async with self.db_manager.get_session() as session:
            stmt = select(
                func.count().label('total_count'),
                func.avg(ExpressionPattern.weight).label('avg_weight'),
                func.min(ExpressionPattern.last_active_time).label('oldest_time'),
                func.max(ExpressionPattern.last_active_time).label('newest_time'),
            ).select_from(ExpressionPattern)
            if group_id:
                stmt = stmt.where(ExpressionPattern.group_id == group_id)

            row = (await session.execute(stmt)).one_or_none()
            if not row or not row.total_count:
                return None

            cfg = self.decay_configs.get('expression_patterns', DecayConfig(decay_days=15))
            oldest_days = (current_time - row.oldest_time) / (24 * 3600) if row.oldest_time else 0
            newest_days = (current_time - row.newest_time) / (24 * 3600) if row.newest_time else 0

            return {
                'total_count': row.total_count,
                'avg_weight': round(row.avg_weight, 3) if row.avg_weight else 0,
                'oldest_days': round(oldest_days, 1),
                'newest_days': round(newest_days, 1),
                'decay_config': {'decay_days': cfg.decay_days, 'decay_min': cfg.decay_min},
            }

    async def schedule_decay_maintenance(self, interval_hours: int = 24):
        """
        定期衰减维护任务

        Args:
            interval_hours: 维护间隔小时数
        """
        logger.info(f"启动定期衰减维护，间隔: {interval_hours}小时")

        while self._status == ServiceLifecycle.RUNNING:
            try:
                results = await self.apply_decay_to_all_tables()

                total_updated = sum(r[0] for r in results.values())
                total_deleted = sum(r[1] for r in results.values())

                if total_updated > 0 or total_deleted > 0:
                    logger.info(f"定期衰减维护完成，总计更新: {total_updated}，删除: {total_deleted}")

                await asyncio.sleep(interval_hours * 3600)

            except Exception as e:
                logger.error(f"定期衰减维护失败: {e}")
                await asyncio.sleep(3600)
