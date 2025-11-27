"""
指标分析服务 - 处理智能指标分析相关业务逻辑
"""
from typing import Dict, Any
from astrbot.api import logger


class MetricsService:
    """指标分析服务"""

    def __init__(self, container):
        """
        初始化指标分析服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.intelligence_metrics_service = container.intelligence_metrics_service
        self.database_manager = container.database_manager

    async def get_intelligence_metrics(self, group_id: str = 'default') -> Dict[str, Any]:
        """
        获取智能指标

        Args:
            group_id: 群组ID

        Returns:
            Dict: 智能指标数据
        """
        if not self.intelligence_metrics_service:
            logger.warning("智能指标服务未初始化")
            return {
                'overall_score': 0,
                'dimensions': {},
                'trends': [],
                'message': '智能指标服务未初始化'
            }

        try:
            metrics = await self.intelligence_metrics_service.calculate_metrics(group_id)
            return metrics if metrics else {
                'overall_score': 0,
                'dimensions': {},
                'trends': []
            }
        except Exception as e:
            logger.error(f"获取智能指标失败: {e}", exc_info=True)
            return {
                'overall_score': 0,
                'dimensions': {},
                'trends': [],
                'error': str(e)
            }

    async def get_diversity_metrics(self, group_id: str = 'default') -> Dict[str, Any]:
        """
        获取多样性指标

        Args:
            group_id: 群组ID

        Returns:
            Dict: 多样性指标数据
        """
        if not self.database_manager:
            return {
                'vocabulary_diversity': 0,
                'topic_diversity': 0,
                'style_diversity': 0,
                'total_score': 0
            }

        try:
            diversity = await self.database_manager.get_diversity_metrics(group_id)
            return diversity if diversity else {
                'vocabulary_diversity': 0,
                'topic_diversity': 0,
                'style_diversity': 0,
                'total_score': 0
            }
        except Exception as e:
            logger.error(f"获取多样性指标失败: {e}", exc_info=True)
            return {
                'vocabulary_diversity': 0,
                'topic_diversity': 0,
                'style_diversity': 0,
                'total_score': 0,
                'error': str(e)
            }

    async def get_affection_metrics(self, group_id: str = 'default') -> Dict[str, Any]:
        """
        获取好感度指标

        Args:
            group_id: 群组ID

        Returns:
            Dict: 好感度指标数据
        """
        if not self.database_manager:
            return {
                'average_affection': 0,
                'total_users': 0,
                'high_affection_count': 0,
                'low_affection_count': 0,
                'distribution': []
            }

        try:
            affection = await self.database_manager.get_affection_metrics(group_id)
            return affection if affection else {
                'average_affection': 0,
                'total_users': 0,
                'high_affection_count': 0,
                'low_affection_count': 0,
                'distribution': []
            }
        except Exception as e:
            logger.error(f"获取好感度指标失败: {e}", exc_info=True)
            return {
                'average_affection': 0,
                'total_users': 0,
                'high_affection_count': 0,
                'low_affection_count': 0,
                'distribution': [],
                'error': str(e)
            }
