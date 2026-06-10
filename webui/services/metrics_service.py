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
            # 从数据库收集学习效率计算所需的输入指标
            total_messages = 0
            filtered_messages = 0
            style_patterns = 0
            persona_updates = 0
            affection_users = 0

            db = self.database_manager
            if db:
                try:
                    detailed = await db.get_detailed_metrics(group_id)
                    if isinstance(detailed, dict):
                        msgs = detailed.get('messages', {}) or {}
                        learning = detailed.get('learning', {}) or {}
                        total_messages = int(msgs.get('raw', 0) or 0)
                        filtered_messages = int(msgs.get('filtered', 0) or 0)
                        style_patterns = int(learning.get('style_patterns', 0) or 0)
                        persona_updates = int(learning.get('persona_reviews', 0) or 0)
                except Exception as e:
                    logger.warning(f"获取详细指标失败: {e}")

                try:
                    affections = await db.get_all_user_affections(group_id)
                    affection_users = len(affections) if affections else 0
                except Exception as e:
                    logger.warning(f"获取好感度用户数失败: {e}")

            metrics = await self.intelligence_metrics_service.calculate_learning_efficiency(
                total_messages=total_messages,
                filtered_messages=filtered_messages,
                style_patterns_learned=style_patterns,
                persona_updates_count=persona_updates,
                affection_users_count=affection_users,
            )

            return {
                'overall_score': round(metrics.overall_efficiency, 1),
                'dimensions': {
                    'message_filter_rate': round(metrics.message_filter_rate, 1),
                    'content_refine_quality': round(metrics.content_refine_quality, 1),
                    'style_learning_progress': round(metrics.style_learning_progress, 1),
                    'persona_update_quality': round(metrics.persona_update_quality, 1),
                    'jargon_learning_score': round(metrics.jargon_learning_score, 1),
                    'social_relation_score': round(metrics.social_relation_score, 1),
                    'affection_score': round(metrics.affection_score, 1),
                    'active_strategies_count': metrics.active_strategies_count,
                },
                'trends': [],
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
            # 当前架构没有独立的多样性数据源，基于已学到的风格模式做近似估算
            style_patterns = 0
            detailed = await self.database_manager.get_detailed_metrics(group_id)
            if isinstance(detailed, dict):
                learning = detailed.get('learning', {}) or {}
                style_patterns = int(learning.get('style_patterns', 0) or 0)

            style_diversity = min(style_patterns * 2, 100)
            vocabulary_diversity = 0
            topic_diversity = 0
            total_score = round(
                (style_diversity + vocabulary_diversity + topic_diversity) / 3, 1
            )

            return {
                'vocabulary_diversity': vocabulary_diversity,
                'topic_diversity': topic_diversity,
                'style_diversity': style_diversity,
                'total_score': total_score,
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
            affections = await self.database_manager.get_all_user_affections(group_id)
            affections = affections or []

            levels = []
            for item in affections:
                try:
                    levels.append(int(item.get('affection_level', 0) or 0))
                except (TypeError, ValueError):
                    continue

            total_users = len(levels)
            average_affection = round(sum(levels) / total_users, 1) if total_users else 0
            high_affection_count = sum(1 for lvl in levels if lvl >= 70)
            low_affection_count = sum(1 for lvl in levels if lvl <= 30)

            # 好感度分布 (0-20, 21-40, 41-60, 61-80, 81-100)
            buckets = [
                ('0-20', 0, 20),
                ('21-40', 21, 40),
                ('41-60', 41, 60),
                ('61-80', 61, 80),
                ('81-100', 81, 100),
            ]
            distribution = [
                {
                    'range': label,
                    'count': sum(1 for lvl in levels if low <= lvl <= high),
                }
                for label, low, high in buckets
            ]

            return {
                'average_affection': average_affection,
                'total_users': total_users,
                'high_affection_count': high_affection_count,
                'low_affection_count': low_affection_count,
                'distribution': distribution,
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
