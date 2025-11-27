"""
学习功能蓝图 - 处理风格学习相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.learning_service import LearningService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

learning_bp = Blueprint('learning', __name__, url_prefix='/api')


@learning_bp.route("/style_learning/results", methods=["GET"])
@require_auth
async def get_style_learning_results():
    """获取风格学习结果"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        results_data = await learning_service.get_style_learning_results()

        return jsonify(results_data), 200

    except Exception as e:
        logger.error(f"获取风格学习结果失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/reviews", methods=["GET"])
@require_auth
async def get_style_learning_reviews():
    """获取对话风格学习审查列表"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        reviews_data = await learning_service.get_style_learning_reviews(limit=50)

        return jsonify(reviews_data), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取风格学习审查列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>/approve", methods=["POST"])
@require_auth
async def approve_style_learning_review(review_id: int):
    """批准对话风格学习审查 - 使用与人格学习审查相同的备份逻辑"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        success, message = await learning_service.approve_style_learning_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            if '不存在' in message:
                return error_response(message, 404)
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"批准风格学习审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>/reject", methods=["POST"])
@require_auth
async def reject_style_learning_review(review_id: int):
    """拒绝对话风格学习审查"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        success, message = await learning_service.reject_style_learning_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"拒绝风格学习审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/patterns", methods=["GET"])
@require_auth
async def get_style_learning_patterns():
    """获取风格学习模式"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        patterns_data = await learning_service.get_style_learning_patterns()

        return jsonify(patterns_data), 200

    except Exception as e:
        logger.error(f"获取学习模式失败: {e}", exc_info=True)
        return error_response(str(e), 500)
