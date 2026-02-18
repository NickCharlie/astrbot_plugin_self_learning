"""
黑话管理蓝图 - 处理黑话学习相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.jargon_service import JargonService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

jargon_bp = Blueprint('jargon', __name__, url_prefix='/api')


@jargon_bp.route("/jargon/stats", methods=["GET"])
@require_auth
async def get_jargon_stats():
    """获取黑话统计信息"""
    try:
        container = get_container()
        jargon_service = JargonService(container)
        stats = await jargon_service.get_jargon_stats()

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"获取黑话统计失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/list", methods=["GET"])
@require_auth
async def get_jargon_list():
    """获取黑话列表"""
    try:
        group_id = request.args.get('group_id')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))

        container = get_container()
        jargon_service = JargonService(container)
        result = await jargon_service.get_jargon_list(group_id, page, page_size)

        return jsonify(result), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取黑话列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/search", methods=["GET"])
@require_auth
async def search_jargon():
    """搜索黑话"""
    try:
        keyword = request.args.get('keyword', '').strip()
        if not keyword:
            return error_response("搜索关键词不能为空", 400)

        container = get_container()
        jargon_service = JargonService(container)
        results = await jargon_service.search_jargon(keyword)

        return jsonify({
            'jargons': results,
            'total': len(results)
        }), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"搜索黑话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/<int:jargon_id>", methods=["DELETE"])
@require_auth
async def delete_jargon(jargon_id: int):
    """删除黑话"""
    try:
        container = get_container()
        jargon_service = JargonService(container)
        success, message = await jargon_service.delete_jargon(jargon_id)

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"删除黑话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/<int:jargon_id>/toggle_global", methods=["POST"])
@require_auth
async def toggle_jargon_global(jargon_id: int):
    """切换黑话的全局状态"""
    try:
        container = get_container()
        jargon_service = JargonService(container)
        success, message, new_status = await jargon_service.toggle_jargon_global(jargon_id)

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'is_global': new_status
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"切换黑话全局状态失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/groups", methods=["GET"])
@require_auth
async def get_jargon_groups():
    """获取包含黑话的群组列表"""
    try:
        container = get_container()
        jargon_service = JargonService(container)
        groups = await jargon_service.get_jargon_groups()

        return jsonify({
            'groups': groups,
            'total': len(groups)
        }), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取黑话群组列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/sync_to_group", methods=["POST"])
@require_auth
async def sync_global_jargon_to_group():
    """同步全局黑话到指定群组"""
    try:
        data = await request.get_json()
        target_group_id = data.get('group_id')

        if not target_group_id:
            return error_response("群组ID不能为空", 400)

        container = get_container()
        jargon_service = JargonService(container)
        success, message, count = await jargon_service.sync_global_to_group(target_group_id)

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'synced_count': count
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"同步全局黑话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/global", methods=["GET"])
@require_auth
async def get_global_jargon_list():
    """获取全局共享的黑话列表"""
    try:
        limit = request.args.get('limit', 50, type=int)

        container = get_container()
        database_manager = container.database_manager
        if not database_manager:
            return jsonify({"success": False, "error": "数据库管理器未初始化"}), 500

        jargon_list = await database_manager.get_global_jargon_list(limit=limit)

        return jsonify({
            "success": True,
            "data": jargon_list,
            "total": len(jargon_list)
        }), 200
    except Exception as e:
        logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/<int:jargon_id>/set_global", methods=["POST"])
@require_auth
async def set_jargon_global_status(jargon_id: int):
    """设置黑话的全局共享状态"""
    try:
        container = get_container()
        database_manager = container.database_manager
        if not database_manager:
            return jsonify({"success": False, "error": "数据库管理器未初始化"}), 500

        data = await request.get_json()
        is_global = data.get('is_global', True)

        result = await database_manager.set_jargon_global(jargon_id, is_global)

        if result:
            status_text = "全局共享" if is_global else "取消全局共享"
            return jsonify({
                "success": True,
                "message": f"黑话已{status_text}",
                "is_global": is_global
            }), 200
        else:
            return jsonify({"success": False, "error": "操作失败"}), 500
    except Exception as e:
        logger.error(f"设置黑话全局状态失败: {e}", exc_info=True)
        return error_response(str(e), 500)
