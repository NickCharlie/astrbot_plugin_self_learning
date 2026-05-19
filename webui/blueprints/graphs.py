"""
Dashboard graph blueprint.
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..services.graph_service import GraphService
from ..utils.response import error_response

graphs_bp = Blueprint('graphs', __name__, url_prefix='/api')


def _parse_limit(default: int = 120) -> int:
    try:
        return int(request.args.get('limit', default))
    except (TypeError, ValueError):
        return default


@graphs_bp.route("/graphs/memory", methods=["GET"])
@require_auth
async def get_memory_graph():
    """获取记忆图可视化数据。"""
    try:
        container = get_container()
        service = GraphService(container)
        payload = await service.get_memory_graph(
            group_id=request.args.get('group_id') or None,
            limit=_parse_limit(),
        )
        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"获取记忆图失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@graphs_bp.route("/graphs/knowledge", methods=["GET"])
@require_auth
async def get_knowledge_graph():
    """获取知识图谱可视化数据。"""
    try:
        container = get_container()
        service = GraphService(container)
        payload = await service.get_knowledge_graph(
            group_id=request.args.get('group_id') or None,
            limit=_parse_limit(),
        )
        return jsonify(payload), 200
    except Exception as e:
        logger.error(f"获取知识图谱失败: {e}", exc_info=True)
        return error_response(str(e), 500)
