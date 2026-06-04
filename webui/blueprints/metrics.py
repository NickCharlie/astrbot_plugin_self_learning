"""
指标分析蓝图 - 处理指标分析相关路由
"""
from typing import Any, Dict

from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.metrics_service import MetricsService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

metrics_bp = Blueprint('metrics', __name__, url_prefix='/api')


def _get_cache_manager_instance():
    """Return the plugin cache manager, if available."""
    try:
        from ...utils.cache_manager import get_cache_manager

        return get_cache_manager()
    except Exception as e:
        logger.warning(f"获取缓存管理器失败: {e}")
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _get_cache_hit_payload(cache_manager=None) -> Dict[str, Any]:
    """Build API payload from CacheManager.get_hit_rates()."""
    manager = cache_manager if cache_manager is not None else _get_cache_manager_instance()
    if not manager or not hasattr(manager, "get_hit_rates"):
        return {
            "cache_hit_rates": {},
            "cache_hit_summary": {
                "available": False,
                "total_hits": 0,
                "total_misses": 0,
                "total_queries": 0,
                "hit_rate": 0.0,
                "message": "cache manager unavailable",
            },
        }

    try:
        raw_rates = manager.get_hit_rates() or {}
    except Exception as e:
        logger.warning(f"获取缓存命中统计失败: {e}")
        return {
            "cache_hit_rates": {},
            "cache_hit_summary": {
                "available": False,
                "total_hits": 0,
                "total_misses": 0,
                "total_queries": 0,
                "hit_rate": 0.0,
                "message": str(e),
            },
        }

    rates: Dict[str, Dict[str, Any]] = {}
    total_hits = 0
    total_misses = 0
    for name, stats in raw_rates.items():
        if not isinstance(stats, dict):
            continue
        hits = _safe_int(stats.get("hits"))
        misses = _safe_int(stats.get("misses"))
        total = hits + misses
        api_hit_rate = _safe_float(stats.get("hit_rate"))
        hit_rate = api_hit_rate if total else 0.0
        rates[str(name)] = {
            "hits": hits,
            "misses": misses,
            "total_queries": total,
            "hit_rate": round(hit_rate, 4),
        }
        total_hits += hits
        total_misses += misses

    total_queries = total_hits + total_misses
    return {
        "cache_hit_rates": rates,
        "cache_hit_summary": {
            "available": True,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_queries": total_queries,
            "hit_rate": round(total_hits / total_queries, 4) if total_queries else 0.0,
        },
    }


@metrics_bp.route("/intelligence_metrics", methods=["GET"])
@require_auth
async def get_intelligence_metrics():
    """获取智能指标"""
    try:
        group_id = request.args.get('group_id', 'default')

        container = get_container()
        metrics_service = MetricsService(container)
        metrics = await metrics_service.get_intelligence_metrics(group_id)

        return jsonify(metrics), 200

    except Exception as e:
        logger.error(f"获取智能指标失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@metrics_bp.route("/diversity_metrics", methods=["GET"])
@require_auth
async def get_diversity_metrics():
    """获取多样性指标"""
    try:
        group_id = request.args.get('group_id', 'default')

        container = get_container()
        metrics_service = MetricsService(container)
        diversity = await metrics_service.get_diversity_metrics(group_id)

        return jsonify(diversity), 200

    except Exception as e:
        logger.error(f"获取多样性指标失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@metrics_bp.route("/affection_metrics", methods=["GET"])
@require_auth
async def get_affection_metrics():
    """获取好感度指标"""
    try:
        group_id = request.args.get('group_id', 'default')

        container = get_container()
        metrics_service = MetricsService(container)
        affection = await metrics_service.get_affection_metrics(group_id)

        return jsonify(affection), 200

    except Exception as e:
        logger.error(f"获取好感度指标失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@metrics_bp.route("/metrics", methods=["GET"])
@require_auth
async def get_metrics():
    """获取聚合性能指标"""
    try:
        container = get_container()
        database_manager = container.database_manager

        # Message statistics
        total_messages = 0
        filtered_messages = 0
        if database_manager:
            try:
                stats = await database_manager.get_messages_statistics()
                if isinstance(stats, dict):
                    total_messages = int(stats.get('total_messages', 0) or 0)
                    filtered_messages = int(stats.get('filtered_messages', 0) or 0)
            except Exception as e:
                logger.warning(f"获取消息统计失败: {e}")

        # LLM call statistics (filter out providers with no calls)
        llm_stats = {}
        llm_call_breakdown = []
        llm_call_summary = {
            "total_calls": 0,
            "provider_count": 0,
            "abnormal_provider_count": 0,
            "average_calls_per_provider": 0.0,
            "abnormal_threshold_calls": 0.0,
            "abnormal_threshold_ratio": 1.5,
            "minimum_abnormal_calls": 5,
        }
        filter_model_summary = {
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
            "abnormal_threshold_ratio": 1.5,
            "minimum_abnormal_calls": 5,
            "is_abnormal": False,
            "abnormal_reason": "",
            "configured": False,
        }
        llm_adapter = container.llm_adapter
        if llm_adapter and hasattr(llm_adapter, 'get_call_statistics'):
            try:
                real_stats = llm_adapter.get_call_statistics()
                provider_info = {}
                if hasattr(llm_adapter, 'get_provider_info'):
                    try:
                        provider_info = llm_adapter.get_provider_info() or {}
                    except Exception as e:
                        logger.warning(f"获取LLM提供商信息失败: {e}")

                provider_rows = []
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
                            "provider_label": provider_info.get(provider_type, provider_type),
                            "total_calls": total_calls,
                            "avg_response_time_ms": round(float(stats_data.get('avg_response_time_ms', 0) or 0), 2),
                            "success_rate": round(float(stats_data.get('success_rate', 1.0) or 0), 4),
                            "error_count": int(stats_data.get('error_count', 0) or 0),
                        })

                provider_count = len(provider_rows)
                total_calls = sum(row["total_calls"] for row in provider_rows)
                average_calls = (total_calls / provider_count) if provider_count else 0.0
                abnormal_threshold_ratio = 1.5
                minimum_abnormal_calls = 5
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
            except Exception as e:
                logger.warning(f"获取LLM统计失败: {e}")

        # System metrics (simplified, no psutil dependency)
        system_metrics = {
            "cpu_percent": 0,
            "memory_percent": 0,
            "disk_usage_percent": 0
        }
        try:
            import psutil
            system_metrics["cpu_percent"] = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            system_metrics["memory_percent"] = memory.percent
            system_metrics["memory_used_gb"] = round(memory.used / (1024**3), 2)
            system_metrics["memory_total_gb"] = round(memory.total / (1024**3), 2)
            disk = psutil.disk_usage('/')
            system_metrics["disk_usage_percent"] = round(disk.used / disk.total * 100, 2)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"获取系统指标失败: {e}")

        # Learning sessions
        learning_sessions = {"active_sessions": 0, "total_sessions_today": 0}
        progressive_learning = container.progressive_learning
        if progressive_learning:
            try:
                active_count = sum(1 for active in progressive_learning.learning_active.values() if active)
                learning_sessions["active_sessions"] = active_count
            except Exception:
                pass

        # Learning efficiency (from persistent DB data)
        learning_efficiency = 0
        learning_dimensions = {}

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

        # Hook performance timing
        hook_performance = {}
        perf_collector = container.perf_collector
        if perf_collector and hasattr(perf_collector, 'get_perf_data'):
            try:
                hook_performance = perf_collector.get_perf_data(recent_limit=50)
            except Exception as e:
                logger.warning(f"获取Hook性能数据失败: {e}")

        cache_hit_payload = _get_cache_hit_payload()

        import time
        metrics = {
            "llm_calls": llm_stats,
            "llm_call_breakdown": llm_call_breakdown,
            "llm_call_summary": llm_call_summary,
            "filter_model_summary": filter_model_summary,
            "total_messages_collected": total_messages,
            "filtered_messages": filtered_messages,
            "system_metrics": system_metrics,
            "learning_sessions": learning_sessions,
            "learning_efficiency": round(learning_efficiency, 1),
            "learning_dimensions": learning_dimensions,
            "hook_performance": hook_performance,
            **cache_hit_payload,
            "last_updated": time.time()
        }

        return jsonify(metrics), 200
    except Exception as e:
        logger.error(f"获取指标失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@metrics_bp.route("/metrics/trends", methods=["GET"])
@require_auth
async def get_metrics_trends():
    """获取指标趋势数据"""
    try:
        trends_data = {
            'message_growth': 0,
            'filtered_growth': 0,
            'llm_growth': 0,
            'sessions_growth': 0
        }

        container = get_container()
        database_manager = container.database_manager
        if database_manager:
            try:
                real_trends = await database_manager.get_trends_data()
                if real_trends and isinstance(real_trends, dict):
                    trends_data.update(real_trends)
            except Exception as e:
                logger.warning(f"无法从数据库获取趋势数据: {e}")

        return jsonify(trends_data), 200
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@metrics_bp.route("/analytics/trends", methods=["GET"])
@require_auth
async def get_analytics_trends():
    """获取分析趋势数据（24小时趋势 + 7天趋势 + 热力图）"""
    try:
        import random
        from datetime import datetime, timedelta

        # Generate 24-hour trend data
        hours_data = []
        base_time = datetime.now() - timedelta(hours=23)
        for i in range(24):
            current_time = base_time + timedelta(hours=i)
            hours_data.append({
                "time": current_time.strftime("%H:%M"),
                "raw_messages": random.randint(10, 60),
                "filtered_messages": random.randint(5, 30),
                "llm_calls": random.randint(2, 15),
                "response_time": random.randint(400, 1500)
            })

        # Generate 7-day data
        days_data = []
        base_date = datetime.now() - timedelta(days=6)
        for i in range(7):
            current_date = base_date + timedelta(days=i)
            days_data.append({
                "date": current_date.strftime("%m-%d"),
                "total_messages": random.randint(200, 800),
                "learning_sessions": random.randint(5, 20),
                "persona_updates": random.randint(0, 5),
                "success_rate": round(random.uniform(0.7, 0.95), 2)
            })

        # Activity heatmap
        heatmap_data = []
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for day_idx in range(7):
            for hour in range(24):
                activity_level = random.randint(0, 50)
                if 9 <= hour <= 18 and day_idx < 5:
                    activity_level = random.randint(20, 50)
                elif 19 <= hour <= 23 or day_idx >= 5:
                    activity_level = random.randint(10, 35)
                heatmap_data.append([hour, day_idx, activity_level])

        return jsonify({
            "hourly_trends": hours_data,
            "daily_trends": days_data,
            "activity_heatmap": {
                "data": heatmap_data,
                "days": days,
                "hours": [f"{i}:00" for i in range(24)]
            }
        }), 200
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)
