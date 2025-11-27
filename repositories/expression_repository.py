"""
表达模式相关的 Repository
提供表达模式的数据访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, distinct
from typing import List, Dict, Any
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import ExpressionPattern


class ExpressionPatternRepository(BaseRepository[ExpressionPattern]):
    """表达模式 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ExpressionPattern)

    async def get_patterns_by_group(
        self,
        group_id: str,
        limit: int = 10
    ) -> List[ExpressionPattern]:
        """
        获取指定群组的表达模式

        Args:
            group_id: 群组ID
            limit: 最大返回数量

        Returns:
            List[ExpressionPattern]: 表达模式列表（按权重降序）
        """
        try:
            stmt = select(ExpressionPattern).where(
                ExpressionPattern.group_id == group_id
            ).order_by(
                desc(ExpressionPattern.weight)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ExpressionPatternRepository] 获取群组表达模式失败: {e}")
            return []

    async def get_all_patterns(self) -> Dict[str, List[ExpressionPattern]]:
        """
        获取所有群组的表达模式

        Returns:
            Dict[str, List[ExpressionPattern]]: 群组ID -> 表达模式列表的映射
        """
        try:
            stmt = select(ExpressionPattern).order_by(
                ExpressionPattern.group_id,
                desc(ExpressionPattern.weight)
            )

            result = await self.session.execute(stmt)
            all_patterns = list(result.scalars().all())

            # 按群组ID分组
            patterns_by_group = {}
            for pattern in all_patterns:
                if pattern.group_id not in patterns_by_group:
                    patterns_by_group[pattern.group_id] = []
                patterns_by_group[pattern.group_id].append(pattern)

            return patterns_by_group

        except Exception as e:
            logger.error(f"[ExpressionPatternRepository] 获取所有表达模式失败: {e}")
            return {}

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取表达模式统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            # 获取总数
            count_stmt = select(func.count(ExpressionPattern.id))
            count_result = await self.session.execute(count_stmt)
            total_count = count_result.scalar() or 0

            # 获取平均权重
            avg_stmt = select(func.avg(ExpressionPattern.weight))
            avg_result = await self.session.execute(avg_stmt)
            avg_weight = avg_result.scalar() or 0.0

            # 获取群组数量
            group_count_stmt = select(func.count(distinct(ExpressionPattern.group_id)))
            group_count_result = await self.session.execute(group_count_stmt)
            group_count = group_count_result.scalar() or 0

            # 获取最新更新时间
            latest_stmt = select(func.max(ExpressionPattern.last_active_time))
            latest_result = await self.session.execute(latest_stmt)
            latest_time = latest_result.scalar() or 0

            return {
                'total_count': total_count,
                'avg_weight': float(avg_weight),
                'group_count': group_count,
                'latest_time': float(latest_time)
            }

        except Exception as e:
            logger.error(f"[ExpressionPatternRepository] 获取统计信息失败: {e}")
            return {
                'total_count': 0,
                'avg_weight': 0.0,
                'group_count': 0,
                'latest_time': 0
            }

    async def get_top_patterns(self, limit: int = 10) -> List[ExpressionPattern]:
        """
        获取权重最高的表达模式

        Args:
            limit: 最大返回数量

        Returns:
            List[ExpressionPattern]: 表达模式列表
        """
        try:
            stmt = select(ExpressionPattern).order_by(
                desc(ExpressionPattern.weight)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ExpressionPatternRepository] 获取最佳表达模式失败: {e}")
            return []
