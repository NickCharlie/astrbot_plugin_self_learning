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
