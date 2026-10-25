"""情绪板块 API：状态聚合、走向分析与治理操作。"""

from astrbot.api import logger
from ..compat import Blueprint, jsonify, request
from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..utils.response import error_response
from ..services.emotion_board_service import EmotionBoardService

emotion_bp = Blueprint("emotion", __name__, url_prefix="/api")


def _service() -> EmotionBoardService:
    return EmotionBoardService(get_container())


@emotion_bp.route("/emotion/board", methods=["GET"])
@require_auth
async def get_emotion_board():
    try:
        return jsonify({"success": True, "data": await _service().get_board()}), 200
    except Exception as exc:
        logger.error(f"读取情绪板块失败: {exc}", exc_info=True)
        return error_response("读取情绪板块失败: 请稍后重试", 500)


@emotion_bp.route("/emotion/trends", methods=["GET"])
@require_auth
async def get_emotion_trends():
    try:
        raw_days = request.args.get("days", "14")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 14
        return jsonify({"success": True, "data": await _service().get_trends(days)}), 200
    except Exception as exc:
        logger.error(f"读取情绪走向失败: {exc}", exc_info=True)
        return error_response("读取情绪走向失败: 请稍后重试", 500)


@emotion_bp.route("/emotion/action", methods=["POST"])
@require_auth
async def run_emotion_action():
    try:
        body = await request.get_json(silent=True) or {}
        result = await _service().run_action(body)
        return jsonify({
            "success": bool(result.get("success")),
            "message": result.get("message", ""),
            "data": result,
        }), 200
    except Exception as exc:
        logger.error(f"情绪板块操作失败: {exc}", exc_info=True)
        return error_response("情绪板块操作失败: 请稍后重试", 500)
