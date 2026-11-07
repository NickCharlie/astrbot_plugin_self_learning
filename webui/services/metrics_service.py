"""
指标分析服务 - 处理智能指标分析相关业务逻辑
"""
from collections.abc import Mapping
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


# ── /api/metrics 汇总口径 ──
# 独立 WebUI 蓝图（webui/blueprints/metrics.py）与内嵌插件页桥接（core/page_api.py）
# 共用以下函数，保证两端「学习效率」「模型调用异常」等读数同源同口径。

LLM_ABNORMAL_THRESHOLD_RATIO = 1.5
LLM_MINIMUM_ABNORMAL_CALLS = 5


def empty_llm_call_summary() -> Dict[str, Any]:
    """无调用数据时的模型调用汇总。"""
    return {
        "total_calls": 0,
        "provider_count": 0,
        "abnormal_provider_count": 0,
        "average_calls_per_provider": 0.0,
        "abnormal_threshold_calls": 0.0,
        "abnormal_threshold_ratio": LLM_ABNORMAL_THRESHOLD_RATIO,
        "minimum_abnormal_calls": LLM_MINIMUM_ABNORMAL_CALLS,
    }


def empty_filter_model_summary() -> Dict[str, Any]:
    """未配置/未调用筛选模型时的汇总。"""
    return {
        "provider_type": "filter",
        "provider_label": "",
        "total_calls": 0,
        "avg_response_time_ms": 0.0,
        "success_rate": 1.0,
        "error_count": 0,
        "share_percent": 0.0,
        "peer_provider_count": 0,
        "peer_average_calls": 0.0,
        "abnormal_threshold_calls": 0.0,
        "abnormal_threshold_ratio": LLM_ABNORMAL_THRESHOLD_RATIO,
        "minimum_abnormal_calls": LLM_MINIMUM_ABNORMAL_CALLS,
        "is_abnormal": False,
        "abnormal_reason": "",
        "configured": False,
    }


def summarize_llm_call_statistics(real_stats: Any, provider_info: Any = None) -> Dict[str, Any]:
    """把 LLM 适配器的原始调用统计整理为 /api/metrics 的模型调用字段。

    返回 ``llm_calls`` / ``llm_call_breakdown`` / ``llm_call_summary`` /
    ``filter_model_summary``。无调用的 Provider 被过滤；存在多个 Provider 时，
    调用量不低于 ``max(5, 均值 × 1.5)`` 的 Provider 标记为异常。
    """
    llm_stats: Dict[str, Any] = {}
    llm_call_breakdown: List[Dict[str, Any]] = []
    llm_call_summary = empty_llm_call_summary()
    filter_model_summary = empty_filter_model_summary()

    def _result() -> Dict[str, Any]:
        return {
            "llm_calls": llm_stats,
            "llm_call_breakdown": llm_call_breakdown,
            "llm_call_summary": llm_call_summary,
            "filter_model_summary": filter_model_summary,
        }

    if not isinstance(real_stats, Mapping):
        return _result()
    labels = provider_info if isinstance(provider_info, Mapping) else {}

    provider_rows: List[Dict[str, Any]] = []
    for provider_type, stats_data in real_stats.items():
        if provider_type == 'overall' or not isinstance(stats_data, dict):
            continue

        total_calls = int(stats_data.get('total_calls', 0) or 0)
        if total_calls > 0:
            llm_stats[f"{provider_type}_provider"] = {
                "total_calls": total_calls,
                "avg_response_time_ms": stats_data.get('avg_response_time_ms', 0),
                "success_rate": stats_data.get('success_rate', 1.0),
                "error_count": stats_data.get('error_count', 0)
            }
            provider_rows.append({
                "provider_type": provider_type,
                "provider_label": labels.get(provider_type, provider_type),
                "total_calls": total_calls,
                "avg_response_time_ms": round(float(stats_data.get('avg_response_time_ms', 0) or 0), 2),
                "success_rate": round(float(stats_data.get('success_rate', 1.0) or 0), 4),
                "error_count": int(stats_data.get('error_count', 0) or 0),
            })

    provider_count = len(provider_rows)
    total_calls = sum(row["total_calls"] for row in provider_rows)
    average_calls = (total_calls / provider_count) if provider_count else 0.0
    abnormal_threshold_ratio = LLM_ABNORMAL_THRESHOLD_RATIO
    minimum_abnormal_calls = LLM_MINIMUM_ABNORMAL_CALLS
    abnormal_threshold_calls = max(
        minimum_abnormal_calls,
        average_calls * abnormal_threshold_ratio,
    ) if provider_count > 1 else minimum_abnormal_calls

    abnormal_count = 0
    for row in sorted(provider_rows, key=lambda item: item["total_calls"], reverse=True):
        share_percent = (row["total_calls"] / total_calls * 100.0) if total_calls else 0.0
        is_abnormal = provider_count > 1 and row["total_calls"] >= abnormal_threshold_calls
        if is_abnormal:
            abnormal_count += 1
        row.update({
            "share_percent": round(share_percent, 2),
            "is_abnormal": is_abnormal,
            "abnormal_reason": (
                f"调用量高于均值 {abnormal_threshold_ratio:.1f} 倍"
                if is_abnormal else ""
            ),
        })
        llm_call_breakdown.append(row)

    llm_call_summary = {
        "total_calls": total_calls,
        "provider_count": provider_count,
        "abnormal_provider_count": abnormal_count,
        "average_calls_per_provider": round(average_calls, 2),
        "abnormal_threshold_calls": round(abnormal_threshold_calls, 2),
        "abnormal_threshold_ratio": abnormal_threshold_ratio,
        "minimum_abnormal_calls": minimum_abnormal_calls,
    }

    filter_row = next((row for row in provider_rows if row["provider_type"] == "filter"), None)
    peer_rows = [row for row in provider_rows if row["provider_type"] != "filter"]
    peer_provider_count = len(peer_rows)
    peer_total_calls = sum(row["total_calls"] for row in peer_rows)
    peer_average_calls = (peer_total_calls / peer_provider_count) if peer_provider_count else 0.0
    filter_threshold_calls = max(
        minimum_abnormal_calls,
        peer_average_calls * abnormal_threshold_ratio,
    ) if peer_provider_count else minimum_abnormal_calls

    if filter_row:
        filter_is_abnormal = peer_provider_count > 0 and filter_row["total_calls"] >= filter_threshold_calls
        filter_model_summary = {
            "provider_type": "filter",
            "provider_label": filter_row["provider_label"],
            "total_calls": filter_row["total_calls"],
            "avg_response_time_ms": filter_row["avg_response_time_ms"],
            "success_rate": filter_row["success_rate"],
            "error_count": filter_row["error_count"],
            "share_percent": filter_row["share_percent"],
            "peer_provider_count": peer_provider_count,
            "peer_average_calls": round(peer_average_calls, 2),
            "abnormal_threshold_calls": round(filter_threshold_calls, 2),
            "abnormal_threshold_ratio": abnormal_threshold_ratio,
            "minimum_abnormal_calls": minimum_abnormal_calls,
            "is_abnormal": filter_is_abnormal,
            "abnormal_reason": (
                f"筛选模型调用量高于其他模型均值 {abnormal_threshold_ratio:.1f} 倍"
                if filter_is_abnormal else ""
            ),
            "configured": True,
        }

    return _result()


async def compute_learning_efficiency(
    database_manager: Any,
    total_messages: int,
    filtered_messages: int,
) -> Tuple[float, Dict[str, Any]]:
    """按 /api/metrics 口径计算学习效率（0-100）与各维度明细。

    四项各占 25%：消息筛选率、风格审查通过数、表达模式数、学习会话质量。
    数据库不可用时返回 ``(0, {})``；单项读取失败只记录告警并按 0 分计。
    """
    learning_efficiency = 0
    learning_dimensions: Dict[str, Any] = {}

    if database_manager:
        # 1. Message filtering quality
        filter_rate = 0
        if total_messages > 0:
            filter_rate = min(filtered_messages / total_messages * 100, 100)
        learning_dimensions['filter_rate'] = round(filter_rate, 1)

        # 2. Style learning progress
        style_score = 0
        try:
            style_stats = await database_manager.get_style_learning_statistics() if hasattr(database_manager, 'get_style_learning_statistics') else {}
            approved = style_stats.get('approved_reviews', 0) if isinstance(style_stats, dict) else 0
            total_reviews = style_stats.get('total_reviews', 0) if isinstance(style_stats, dict) else 0
            style_score = min(approved * 10, 100)
            learning_dimensions['style_reviews'] = total_reviews
            learning_dimensions['style_approved'] = approved
        except Exception as e:
            logger.warning(f"获取风格学习统计失败: {e}")

        # 3. Expression pattern learning
        pattern_score = 0
        try:
            if hasattr(database_manager, 'get_expression_patterns_statistics'):
                pattern_stats = await database_manager.get_expression_patterns_statistics()
                pattern_count = pattern_stats.get('total_patterns', 0) if isinstance(pattern_stats, dict) else 0
                pattern_score = min(pattern_count * 2, 100)
                learning_dimensions['expression_patterns'] = pattern_count
        except Exception as e:
            logger.warning(f"获取表达模式统计失败: {e}")

        # 4. Learning session quality (from performance records)
        session_quality = 0
        try:
            if hasattr(database_manager, 'get_learning_performance_history'):
                perf_records = await database_manager.get_learning_performance_history('default')
                if perf_records:
                    quality_scores = [r.get('quality_score', 0) for r in perf_records if r.get('quality_score', 0) > 0]
                    if quality_scores:
                        session_quality = min(sum(quality_scores) / len(quality_scores) * 100, 100)
                    success_count = sum(1 for r in perf_records if r.get('success'))
                    learning_dimensions['session_success_rate'] = round(success_count / len(perf_records) * 100, 1) if perf_records else 0
                    learning_dimensions['total_sessions'] = len(perf_records)
        except Exception as e:
            logger.warning(f"获取学习性能记录失败: {e}")

        # Weighted average for learning efficiency
        learning_efficiency = (
            filter_rate * 0.25 +
            style_score * 0.25 +
            pattern_score * 0.25 +
            session_quality * 0.25
        )

        logger.debug(
            f"[Metrics] learning_efficiency={learning_efficiency:.1f} "
            f"(filter={filter_rate:.1f}, style={style_score}, "
            f"pattern={pattern_score}, session_quality={session_quality:.1f})"
        )

    return round(learning_efficiency, 1), learning_dimensions
