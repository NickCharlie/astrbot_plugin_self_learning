"""
指标分析服务 - 处理智能指标分析相关业务逻辑
"""
from typing import Dict, Any, List, Tuple
from astrbot.api import logger


AFFECTION_HIGH_THRESHOLD = 70
AFFECTION_LOW_THRESHOLD = 30
AFFECTION_DISTRIBUTION_BUCKETS: Tuple[Tuple[str, int, int], ...] = (
    ('0-20', 0, 20),
    ('21-40', 21, 40),
    ('41-60', 41, 60),
    ('61-80', 61, 80),
    ('81-100', 81, 100),
)


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
            efficiency_method = getattr(
                self.intelligence_metrics_service,
                'calculate_learning_efficiency',
                None,
            )
            if callable(efficiency_method):
                learning_inputs = await self._collect_learning_efficiency_inputs(group_id)
                try:
                    metrics = await efficiency_method(
                        total_messages=learning_inputs['total_messages'],
                        filtered_messages=learning_inputs['filtered_messages'],
                        style_patterns_learned=learning_inputs['style_patterns'],
                        persona_updates_count=learning_inputs['persona_updates'],
                        affection_users_count=learning_inputs['affection_users'],
                    )
                except TypeError:
                    metrics = await efficiency_method()
                return {
                    'overall_score': round(getattr(metrics, 'overall_efficiency', 0), 1),
                    'dimensions': {
                        'message_filter_rate': round(getattr(metrics, 'message_filter_rate', 0), 1),
                        'content_refine_quality': round(getattr(metrics, 'content_refine_quality', 0), 1),
                        'style_learning_progress': round(getattr(metrics, 'style_learning_progress', 0), 1),
                        'persona_update_quality': round(getattr(metrics, 'persona_update_quality', 0), 1),
                        'jargon_learning_score': round(getattr(metrics, 'jargon_learning_score', 0), 1),
                        'social_relation_score': round(getattr(metrics, 'social_relation_score', 0), 1),
                        'affection_score': round(getattr(metrics, 'affection_score', 0), 1),
                        'active_strategies_count': getattr(metrics, 'active_strategies_count', 0),
                    },
                    'trends': [],
                }

            legacy_method = getattr(self.intelligence_metrics_service, 'calculate_metrics', None)
            if not callable(legacy_method):
                logger.warning("智能指标服务缺少可用的计算方法")
                return self._empty_intelligence_metrics(message='智能指标服务方法不兼容')

            metrics = await legacy_method(group_id)
            return metrics if metrics else {
                'overall_score': 0,
                'dimensions': {},
                'trends': [],
            }
        except Exception as e:
            logger.error(f"获取智能指标失败: {e}", exc_info=True)
            return self._empty_intelligence_metrics(error=str(e))

    @staticmethod
    def _empty_intelligence_metrics(**extra: Any) -> Dict[str, Any]:
        data = {
            'overall_score': 0,
            'dimensions': {},
            'trends': [],
        }
        data.update(extra)
        return data

    async def _collect_learning_efficiency_inputs(self, group_id: str) -> Dict[str, int]:
        """收集学习效率计算所需的数据库输入指标。"""
        inputs = {
            'total_messages': 0,
            'filtered_messages': 0,
            'style_patterns': 0,
            'persona_updates': 0,
            'affection_users': 0,
        }

        db = self.database_manager
        if not db:
            return inputs

        try:
            detailed = await db.get_detailed_metrics(group_id)
            if isinstance(detailed, dict):
                msgs = detailed.get('messages', {}) or {}
                learning = detailed.get('learning', {}) or {}
                inputs['total_messages'] = self._safe_int(msgs.get('raw'))
                inputs['filtered_messages'] = self._safe_int(msgs.get('filtered'))
                inputs['style_patterns'] = self._safe_int(learning.get('style_patterns'))
                inputs['persona_updates'] = self._safe_int(learning.get('persona_reviews'))
        except Exception as e:
            logger.warning(f"获取详细指标失败: {e}")

        try:
            affections = await db.get_all_user_affections(group_id)
            inputs['affection_users'] = len(affections) if affections else 0
        except Exception as e:
            logger.warning(f"获取好感度用户数失败: {e}")

        return inputs

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    async def get_diversity_metrics(self, group_id: str = 'default') -> Dict[str, Any]:
        """
        获取多样性指标

        Args:
            group_id: 群组ID

        Returns:
            Dict: 多样性指标数据
        """
        db = self.database_manager
        if not db:
            return {
                'vocabulary_diversity': 0,
                'topic_diversity': 0,
                'style_diversity': 0,
                'total_score': 0
            }

        try:
            # 当前架构没有独立的多样性数据源，基于已学到的风格模式做近似估算
            style_patterns = 0
            detailed = await db.get_detailed_metrics(group_id)
            if isinstance(detailed, dict):
                learning = detailed.get('learning', {}) or {}
                style_patterns = self._safe_int(learning.get('style_patterns'))

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

            levels: List[int] = []
            for item in affections:
                try:
                    levels.append(int(item.get('affection_level', 0) or 0))
                except (TypeError, ValueError):
                    continue

            total_users = len(levels)
            average_affection = round(sum(levels) / total_users, 1) if total_users else 0
            high_affection_count = sum(
                1 for lvl in levels if lvl >= AFFECTION_HIGH_THRESHOLD
            )
            low_affection_count = sum(
                1 for lvl in levels if lvl <= AFFECTION_LOW_THRESHOLD
            )

            distribution = [
                {
                    'range': label,
                    'count': sum(1 for lvl in levels if low <= lvl <= high),
                }
                for label, low, high in AFFECTION_DISTRIBUTION_BUCKETS
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
