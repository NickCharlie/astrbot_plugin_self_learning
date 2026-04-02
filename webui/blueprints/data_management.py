"""
数据管理蓝图 — 各功能模块数据统计与一键清空
"""
from quart import Blueprint, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.data_management_service import DataManagementService
from ..middleware.auth import require_auth
from ..utils.response import error_response

data_management_bp = Blueprint('data_management', __name__, url_prefix='/api/data')


@data_management_bp.route("/statistics", methods=["GET"])
@require_auth
async def get_data_statistics():
    """获取各功能模块数据行数统计"""
    try:
        container = get_container()
        service = DataManagementService(container)
        stats = await service.get_data_statistics()
        return jsonify({'success': True, 'data': stats}), 200
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"获取数据统计失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/messages", methods=["DELETE"])
@require_auth
async def clear_messages():
    """清空所有消息数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_messages()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空消息数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/persona_reviews", methods=["DELETE"])
@require_auth
async def clear_persona_reviews():
    """清空所有人格审查数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_persona_reviews()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空人格审查数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/style_learning", methods=["DELETE"])
@require_auth
async def clear_style_learning():
    """清空所有对话风格学习数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_style_learning()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空风格学习数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/jargon", methods=["DELETE"])
@require_auth
async def clear_jargon():
    """清空所有黑话数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_jargon()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空黑话数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/learning_history", methods=["DELETE"])
@require_auth
async def clear_learning_history():
    """清空所有学习历史数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_learning_history()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空学习历史数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@data_management_bp.route("/clear/all", methods=["DELETE"])
@require_auth
async def clear_all_data():
    """一键清空所有插件数据"""
    try:
        container = get_container()
        service = DataManagementService(container)
        success, message, deleted = await service.clear_all()
        if success:
            return jsonify({'success': True, 'message': message, 'deleted': deleted}), 200
        return error_response(message, 500)
    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"清空全部数据失败: {e}", exc_info=True)
        return error_response(str(e), 500)
