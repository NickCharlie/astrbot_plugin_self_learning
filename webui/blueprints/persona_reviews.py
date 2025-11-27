"""
人格审查蓝图 - 处理人格更新审查相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.persona_review_service import PersonaReviewService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

persona_reviews_bp = Blueprint('persona_reviews', __name__, url_prefix='/api')


@persona_reviews_bp.route("/persona_updates", methods=["GET"])
@require_auth
async def get_pending_persona_updates():
    """获取所有待审查的人格更新 (整合三种数据源)"""
    try:
        container = get_container()
        review_service = PersonaReviewService(container)
        result = await review_service.get_pending_persona_updates()

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"获取待审查人格更新失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/<update_id>/review", methods=["POST"])
@require_auth
async def review_persona_update(update_id: str):
    """审查人格更新内容 (批准/拒绝)"""
    try:
        data = await request.get_json()
        action = data.get("action")
        comment = data.get("comment", "")
        modified_content = data.get("modified_content")

        container = get_container()
        review_service = PersonaReviewService(container)
        success, message = await review_service.review_persona_update(
            update_id, action, comment, modified_content
        )

        if success:
            return jsonify({"success": True, "message": message}), 200
        else:
            return jsonify({"error": message}), 500

    except ValueError as e:
        return jsonify({"error": f"Invalid update_id format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"审查人格更新失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/reviewed", methods=["GET"])
@require_auth
async def get_reviewed_persona_updates():
    """获取已审查的人格更新列表"""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        status_filter = request.args.get('status')

        container = get_container()
        review_service = PersonaReviewService(container)
        result = await review_service.get_reviewed_persona_updates(limit, offset, status_filter)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"获取已审查人格更新失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/<update_id>/revert", methods=["POST"])
@require_auth
async def revert_persona_update(update_id: str):
    """撤回人格更新审查"""
    try:
        data = await request.get_json()
        reason = data.get("reason", "撤回审查决定")

        container = get_container()
        review_service = PersonaReviewService(container)
        success, message = await review_service.revert_persona_update(update_id, reason)

        if success:
            return jsonify({"success": True, "message": message}), 200
        else:
            return jsonify({"error": message}), 500

    except ValueError as e:
        return jsonify({"error": f"Invalid update_id format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"撤回人格更新审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/<update_id>/delete", methods=["POST"])
@require_auth
async def delete_persona_update(update_id: str):
    """删除人格更新审查记录"""
    try:
        container = get_container()
        review_service = PersonaReviewService(container)
        success, message = await review_service.delete_persona_update(update_id)

        if success:
            return jsonify({"success": True, "message": message}), 200
        else:
            return jsonify({"error": message}), 404 if "未找到" in message or "not found" in message.lower() else 500

    except Exception as e:
        logger.error(f"删除人格更新审查记录失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/batch_delete", methods=["POST"])
@require_auth
async def batch_delete_persona_updates():
    """批量删除人格更新审查记录"""
    try:
        data = await request.get_json()
        update_ids = data.get('update_ids', [])

        if not update_ids or not isinstance(update_ids, list):
            return jsonify({"error": "update_ids is required and must be a list"}), 400

        container = get_container()
        review_service = PersonaReviewService(container)
        result = await review_service.batch_delete_persona_updates(update_ids)

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"批量删除人格更新审查记录失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@persona_reviews_bp.route("/persona_updates/batch_review", methods=["POST"])
@require_auth
async def batch_review_persona_updates():
    """批量审查人格更新记录"""
    try:
        data = await request.get_json()
        update_ids = data.get('update_ids', [])
        action = data.get('action')
        comment = data.get('comment', '')

        if not update_ids or not isinstance(update_ids, list):
            return jsonify({"error": "update_ids is required and must be a list"}), 400

        if action not in ['approve', 'reject']:
            return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

        container = get_container()
        review_service = PersonaReviewService(container)
        result = await review_service.batch_review_persona_updates(update_ids, action, comment)

        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"批量审查人格更新记录失败: {e}", exc_info=True)
        return error_response(str(e), 500)
