"""
聊天历史蓝图 - 处理聊天历史相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.chat_service import ChatService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

chat_bp = Blueprint('chat', __name__, url_prefix='/api')


@chat_bp.route("/chat/history", methods=["GET"])
@require_auth
async def get_chat_history():
    """获取聊天历史记录"""
    try:
        group_id = request.args.get('group_id')
        start_time = request.args.get('start_time', type=int)
        end_time = request.args.get('end_time', type=int)
        limit = request.args.get('limit', 100, type=int)

        container = get_container()
        chat_service = ChatService(container)
        history = await chat_service.get_chat_history(
            group_id=group_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return jsonify({
            'history': history,
            'total': len(history)
        }), 200

    except Exception as e:
        logger.error(f"获取聊天历史失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@chat_bp.route("/chat/history/<int:message_id>", methods=["GET"])
@require_auth
async def get_chat_message_detail(message_id: int):
    """获取聊天消息详情"""
    try:
        container = get_container()
        chat_service = ChatService(container)
        message = await chat_service.get_chat_message_detail(message_id)

        if not message:
            return error_response("消息不存在", 404)

        return jsonify(message), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取消息详情失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@chat_bp.route("/chat/history/<int:message_id>", methods=["DELETE"])
@require_auth
async def delete_chat_message(message_id: int):
    """删除聊天消息"""
    try:
        container = get_container()
        chat_service = ChatService(container)
        success, message = await chat_service.delete_chat_message(message_id)

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"删除消息失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@chat_bp.route("/chat/statistics", methods=["GET"])
@require_auth
async def get_chat_statistics():
    """获取聊天统计信息"""
    try:
        group_id = request.args.get('group_id')

        container = get_container()
        chat_service = ChatService(container)
        stats = await chat_service.get_chat_statistics(group_id)

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"获取聊天统计失败: {e}", exc_info=True)
        return error_response(str(e), 500)
