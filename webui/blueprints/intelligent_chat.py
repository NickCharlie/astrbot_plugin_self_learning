"""
智能对话蓝图 - 目标驱动对话接口
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

intelligent_chat_bp = Blueprint('intelligent_chat', __name__, url_prefix='/api/intelligent_chat')


@intelligent_chat_bp.route("/chat", methods=["POST"])
@require_auth
async def chat_with_goal():
    """带目标引导的对话接口"""
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        user_message = data.get('message')
        group_id = data.get('group_id', 'default')
        force_normal_mode = data.get('force_normal_mode', False)

        if not user_id or not user_message:
            return error_response("缺少必要参数: user_id 和 message", 400)

        container = get_container()
        component_factory = container.component_factory
        intelligent_chat_service = component_factory.create_intelligent_chat_service()

        result = await intelligent_chat_service.chat_with_goal(
            user_id=user_id,
            user_message=user_message,
            group_id=group_id,
            force_normal_mode=force_normal_mode
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"智能对话失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@intelligent_chat_bp.route("/goal/status", methods=["GET"])
@require_auth
async def get_goal_status():
    """获取用户当前目标状态"""
    try:
        user_id = request.args.get('user_id')
        group_id = request.args.get('group_id', 'default')

        if not user_id:
            return error_response("缺少user_id参数", 400)

        container = get_container()
        component_factory = container.component_factory
        intelligent_chat_service = component_factory.create_intelligent_chat_service()

        status = await intelligent_chat_service.get_user_goal_status(user_id, group_id)

        return jsonify(status if status else {}), 200

    except Exception as e:
        logger.error(f"获取目标状态失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@intelligent_chat_bp.route("/goal/clear", methods=["DELETE"])
@require_auth
async def clear_goal():
    """清除用户当前目标"""
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        group_id = data.get('group_id', 'default')

        if not user_id:
            return error_response("缺少user_id参数", 400)

        container = get_container()
        component_factory = container.component_factory
        intelligent_chat_service = component_factory.create_intelligent_chat_service()

        success = await intelligent_chat_service.clear_user_goal(user_id, group_id)

        return jsonify({"success": success}), 200

    except Exception as e:
        logger.error(f"清除目标失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@intelligent_chat_bp.route("/goal/statistics", methods=["GET"])
@require_auth
async def get_goal_statistics():
    """获取目标统计信息"""
    try:
        container = get_container()
        component_factory = container.component_factory
        intelligent_chat_service = component_factory.create_intelligent_chat_service()

        stats = await intelligent_chat_service.get_goal_statistics()

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"获取目标统计失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@intelligent_chat_bp.route("/goal/templates", methods=["GET"])
@require_auth
async def get_goal_templates():
    """获取所有可用的目标类型"""
    try:
        from ...services.quality import ConversationGoalManager

        templates = {
            key: {
                "name": value["name"],
                "stages_count": len(value["base_stages"]),
                "min_rounds": value["min_rounds"]
            }
            for key, value in ConversationGoalManager.GOAL_TEMPLATES.items()
        }

        return jsonify({
            "total_types": len(templates),
            "templates": templates
        }), 200

    except Exception as e:
        logger.error(f"获取目标模板失败: {e}", exc_info=True)
        return error_response(str(e), 500)
