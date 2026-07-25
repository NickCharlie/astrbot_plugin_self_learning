"""Shadow-mode management API."""

from astrbot.api import logger
from quart import Blueprint, jsonify, request

try:
    from ...services.shadow_mode import ShadowModeService
except ImportError:
    from services.shadow_mode import ShadowModeService

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..utils.response import error_response


shadow_mode_bp = Blueprint("shadow_mode", __name__, url_prefix="/api")


def _service() -> ShadowModeService:
    return ShadowModeService(getattr(get_container(), "database_manager", None))


@shadow_mode_bp.route("/shadow-mode", methods=["GET"])
@require_auth
async def get_shadow_mode_status():
    try:
        return jsonify({"success": True, "data": await _service().get_status()}), 200
    except Exception as exc:
        logger.error(f"读取影子模式状态失败: {exc}", exc_info=True)
        return error_response(f"读取影子模式状态失败: {exc}", 500)


@shadow_mode_bp.route("/shadow-mode/candidates", methods=["GET"])
@require_auth
async def get_shadow_mode_candidates():
    try:
        data = await _service().list_candidates(
            source_type=request.args.get("source", "live"),
            group_id=request.args.get("group_id", ""),
        )
        return jsonify({"success": True, "data": data}), 200
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        logger.error(f"读取影子模式候选用户失败: {exc}", exc_info=True)
        return error_response(f"读取影子模式候选用户失败: {exc}", 500)


@shadow_mode_bp.route("/shadow-mode/profiles", methods=["POST"])
@require_auth
async def learn_shadow_profile():
    try:
        body = await request.get_json(silent=True) or {}
        profile = await _service().learn(
            source_type=body.get("source_type") or body.get("source") or "live",
            source_group_id=body.get("source_group_id") or body.get("group_id") or "",
            target_group_id=body.get("target_group_id") or body.get("group_id") or "",
            sender_id=body.get("sender_id") or "",
            activate=_body_bool(body, "activate", True),
        )
        return jsonify({"success": True, "data": profile}), 201
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        logger.error(f"学习影子档案失败: {exc}", exc_info=True)
        return error_response(f"学习影子档案失败: {exc}", 500)


@shadow_mode_bp.route("/shadow-mode/profiles/<int:profile_id>", methods=["PUT"])
@require_auth
async def update_shadow_profile(profile_id: int):
    try:
        body = await request.get_json(silent=True) or {}
        profile = await _service().set_enabled(
            profile_id,
            _body_bool(body, "enabled", True),
        )
        return jsonify({"success": True, "data": profile}), 200
    except ValueError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        logger.error(f"更新影子档案失败: {exc}", exc_info=True)
        return error_response(f"更新影子档案失败: {exc}", 500)


def _body_bool(body: dict, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
