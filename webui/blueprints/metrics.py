"""
指标分析蓝图 - 处理指标分析相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.metrics_service import MetricsService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

metrics_bp = Blueprint('metrics', __name__, url_prefix='/api')


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
        llm_adapter = container.llm_adapter
        if llm_adapter and hasattr(llm_adapter, 'get_call_statistics'):
            try:
                real_stats = llm_adapter.get_call_statistics()
                for provider_type, stats_data in real_stats.items():
                    if provider_type != 'overall' and stats_data.get('total_calls', 0) > 0:
                        llm_stats[f"{provider_type}_provider"] = {
                            "total_calls": stats_data.get('total_calls', 0),
                            "avg_response_time_ms": stats_data.get('avg_response_time_ms', 0),
                            "success_rate": stats_data.get('success_rate', 1.0),
                            "error_count": stats_data.get('error_count', 0)
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
            # Message filtering quality
            filter_rate = 0
            if total_messages > 0:
                filter_rate = min(filtered_messages / total_messages * 100, 100)
            learning_dimensions['filter_rate'] = round(filter_rate, 1)

            # Style learning progress
            style_score = 0
            try:
                style_stats = await database_manager.get_style_learning_statistics() if hasattr(database_manager, 'get_style_learning_statistics') else {}
                approved = style_stats.get('approved_reviews', 0) if isinstance(style_stats, dict) else 0
                total_reviews = style_stats.get('total_reviews', 0) if isinstance(style_stats, dict) else 0
                style_score = min(approved * 10, 100)
                learning_dimensions['style_reviews'] = total_reviews
                learning_dimensions['style_approved'] = approved
            except Exception:
                pass

            # Jargon learning
            jargon_score = 0
            try:
                jargon_count = await database_manager.get_jargon_count() if hasattr(database_manager, 'get_jargon_count') else 0
                jargon_score = min(jargon_count * 5, 100)
                learning_dimensions['jargon_count'] = jargon_count
            except Exception:
                pass

            # Social relations
            social_score = 0
            try:
                social_stats = await database_manager.get_social_relationships('default') if hasattr(database_manager, 'get_social_relationships') else []
                social_count = len(social_stats) if isinstance(social_stats, list) else 0
                social_score = min(social_count * 10, 100)
                learning_dimensions['social_relation_count'] = social_count
            except Exception:
                pass

            # Weighted average
            learning_efficiency = (
                filter_rate * 0.25 +
                style_score * 0.30 +
                jargon_score * 0.25 +
                social_score * 0.20
            )
            logger.debug(
                f"[Metrics] learning_efficiency={learning_efficiency:.1f} "
                f"(filter={filter_rate:.1f}, style={style_score}, "
                f"jargon={jargon_score}, social={social_score})"
            )

        # Hook performance timing
        hook_performance = {}
        perf_collector = container.perf_collector
        if perf_collector and hasattr(perf_collector, 'get_perf_data'):
            try:
                hook_performance = perf_collector.get_perf_data(recent_limit=50)
            except Exception as e:
                logger.warning(f"获取Hook性能数据失败: {e}")

        import time
        metrics = {
            "llm_calls": llm_stats,
            "total_messages_collected": total_messages,
            "filtered_messages": filtered_messages,
            "system_metrics": system_metrics,
            "learning_sessions": learning_sessions,
            "learning_efficiency": round(learning_efficiency, 1),
            "learning_dimensions": learning_dimensions,
            "hook_performance": hook_performance,
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
