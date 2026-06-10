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


def _hybrid_success(payload, data=None):
    """Return a success body compatible with both legacy and current frontends."""
    body = dict(payload)
    body['success'] = True
    body['data'] = payload if data is None else data
    return jsonify(body), 200


@jargon_bp.route("/jargon/stats", methods=["GET"])
@require_auth
async def get_jargon_stats():
    """获取黑话统计信息"""
    try:
        group_id = request.args.get('group_id')

        container = get_container()
        jargon_service = JargonService(container)
        stats = await jargon_service.get_jargon_stats(group_id=group_id)

        return _hybrid_success(stats, data=stats)

    except Exception as e:
        logger.error(f"获取黑话统计失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/list", methods=["GET"])
@require_auth
async def get_jargon_list():
    """获取黑话列表"""
    try:
        group_id = request.args.get('group_id')
        page = request.args.get('page', type=int)
        page_size = request.args.get('page_size', type=int)
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int, default=0)

        if page_size is None:
            page_size = limit or 20
        if page is None:
            page = offset // page_size + 1 if page_size > 0 else 1

        # 解析 confirmed 过滤参数
        confirmed_param = request.args.get('confirmed')
        if confirmed_param is None:
            confirmed_param = request.args.get('only_confirmed')
        confirmed = None
        if confirmed_param == 'true':
            confirmed = True
        elif confirmed_param == 'false':
            confirmed = False
        pending_only = str(request.args.get('pending', 'false')).lower() == 'true'

        # 解析 global/local 过滤参数
        filter_param = request.args.get('filter', '').strip().lower()
        global_only = filter_param == 'global'
        local_only = filter_param == 'local'

        # 如果带了 keyword，走搜索逻辑
        keyword = request.args.get('keyword', '').strip()
        container = get_container()
        jargon_service = JargonService(container)

        if keyword:
            results = await jargon_service.search_jargon(
                keyword,
                chat_id=group_id,
                confirmed_only=(confirmed is True),
                unconfirmed_only=(confirmed is False),
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )
            payload = {
                'jargon_list': results,
                'total': len(results),
            }
            return _hybrid_success(payload, data=results)

        result = await jargon_service.get_jargon_list(
            group_id,
            confirmed=confirmed,
            page=page,
            page_size=page_size,
            pending_only=pending_only,
            global_only=global_only,
            local_only=local_only,
        )

        return _hybrid_success(result, data=result.get('jargon_list', []))

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

        group_id = request.args.get('group_id')
        confirmed_param = request.args.get('confirmed_only')
        if confirmed_param is None:
            confirmed_param = request.args.get('confirmed', 'false')
        confirmed_only = str(confirmed_param).lower() == 'true'
        pending_only = str(request.args.get('pending', 'false')).lower() == 'true'
        filter_param = request.args.get('filter', '').strip().lower()

        container = get_container()
        jargon_service = JargonService(container)
        results = await jargon_service.search_jargon(
            keyword,
            chat_id=group_id,
            confirmed_only=confirmed_only,
            pending_only=pending_only,
            global_only=filter_param == 'global',
            local_only=filter_param == 'local',
        )

        payload = {
            'jargon_list': results,
            'total': len(results)
        }
        return _hybrid_success(payload, data=results)

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


@jargon_bp.route("/jargon/<int:jargon_id>", methods=["PUT"])
@require_auth
async def update_jargon(jargon_id: int):
    """编辑黑话"""
    try:
        data = await request.get_json() or {}
        content = data.get('content')
        meaning = data.get('meaning')

        if content is None and meaning is None:
            return error_response('至少需要提供 content 或 meaning', 400)

        container = get_container()
        jargon_service = JargonService(container)
        success, message, item = await jargon_service.update_jargon(
            jargon_id, content=content, meaning=meaning
        )

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'item': item,
                'data': item,
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"编辑黑话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/<int:jargon_id>/review", methods=["POST"])
@require_auth
async def review_jargon(jargon_id: int):
    """确认或驳回黑话候选"""
    try:
        data = await request.get_json() or {}
        action = data.get('action')
        meaning = data.get('meaning')

        container = get_container()
        jargon_service = JargonService(container)
        success, message, item = await jargon_service.review_jargon(
            jargon_id, action, meaning=meaning
        )

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'item': item,
                'data': item,
            }), 200
        return error_response(message, 400 if 'action' in message else 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"审查黑话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/batch_review", methods=["POST"])
@require_auth
async def batch_review_jargon():
    """批量确认或驳回黑话候选"""
    try:
        data = await request.get_json() or {}
        jargon_ids = data.get("jargon_ids") or data.get("ids") or []
        action = data.get("action")
        meaning = data.get("meaning")

        if not jargon_ids or not isinstance(jargon_ids, list):
            return error_response("jargon_ids is required and must be a list", 400)
        if action not in ["approve", "reject"]:
            return error_response("action must be 'approve' or 'reject'", 400)

        container = get_container()
        jargon_service = JargonService(container)
        result = await jargon_service.batch_review_jargon(
            jargon_ids,
            action,
            meaning=meaning,
        )

        if result.get("success"):
            return jsonify(result), 200
        return error_response(result.get("error") or "批量审查失败", 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"批量审查黑话失败: {e}", exc_info=True)
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

        payload = {
            'groups': groups,
            'total': len(groups)
        }
        return _hybrid_success(payload, data=groups)

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
        jargon_service = JargonService(container)
        jargon_list = await jargon_service.get_global_jargon_list(limit=limit)

        payload = {
            'jargon_list': jargon_list,
            'total': len(jargon_list)
        }
        return _hybrid_success(payload, data=jargon_list)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@jargon_bp.route("/jargon/<int:jargon_id>/set_global", methods=["POST"])
@require_auth
async def set_jargon_global_status(jargon_id: int):
    """设置黑话的全局共享状态"""
    try:
        container = get_container()
        jargon_service = JargonService(container)

        data = await request.get_json()
        is_global = data.get('is_global', True)

        # 直接调用数据库方法（set_global 不需要 toggle 逻辑）
        database_manager = container.database_manager
        if not database_manager:
            return error_response("数据库管理器未初始化", 500)

        result = await database_manager.set_jargon_global(jargon_id, is_global)

        if result:
            status_text = "全局共享" if is_global else "取消全局共享"
            return jsonify({
                "success": True,
                "message": f"黑话已{status_text}",
                "is_global": is_global
            }), 200
        else:
            return error_response("操作失败", 500)
    except Exception as e:
        logger.error(f"设置黑话全局状态失败: {e}", exc_info=True)
        return error_response(str(e), 500)
