"""
社交关系蓝图 - 处理社交关系分析相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.social_service import SocialService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

social_bp = Blueprint('social', __name__, url_prefix='/api')


@social_bp.route("/social_relations/<group_id>", methods=["GET"])
@require_auth
async def get_social_relations(group_id: str):
    """获取指定群组的社交关系分析数据"""
    try:
        container = get_container()
        social_service = SocialService(container)
        relations_data = await social_service.get_social_relations(group_id)

        return jsonify(relations_data), 200

    except Exception as e:
        logger.error(f"获取社交关系失败: {e}", exc_info=True)
        return jsonify({
            "group_id": group_id,
            "relations": [],
            "members": [],
            "error": str(e)
        }), 500


@social_bp.route("/social_relations/groups", methods=["GET"])
@require_auth
async def get_available_groups_for_social_analysis():
    """获取可用于社交关系分析的群组列表"""
    try:
        container = get_container()
        social_service = SocialService(container)
        groups = await social_service.get_available_groups()

        return jsonify({
            "success": True,
            "groups": groups,
            "total": len(groups)
        }), 200

    except Exception as e:
        logger.error(f"获取可用群组列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@social_bp.route("/social_relations/<group_id>/analyze", methods=["POST"])
@require_auth
async def trigger_social_relation_analysis(group_id: str):
    """触发群组社交关系分析"""
    try:
        container = get_container()
        social_service = SocialService(container)
        success, message = await social_service.trigger_analysis(group_id)

        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 500

    except Exception as e:
        logger.error(f"触发社交关系分析失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@social_bp.route("/social_relations/<group_id>/clear", methods=["DELETE"])
@require_auth
async def clear_group_social_relations(group_id: str):
    """清空群组社交关系数据"""
    try:
        container = get_container()
        social_service = SocialService(container)
        success, message = await social_service.clear_relations(group_id)

        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 500

    except Exception as e:
        logger.error(f"清空社交关系数据失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@social_bp.route("/social_relations/<group_id>/user/<user_id>", methods=["GET"])
@require_auth
async def get_user_social_relations(group_id: str, user_id: str):
    """获取指定用户的社交关系"""
    try:
        container = get_container()
        social_service = SocialService(container)
        user_relations = await social_service.get_user_relations(group_id, user_id)

        return jsonify(user_relations), 200

    except Exception as e:
        logger.error(f"获取用户社交关系失败: {e}", exc_info=True)
        return jsonify({
            "user_id": user_id,
            "relations": [],
            "error": str(e)
        }), 500
