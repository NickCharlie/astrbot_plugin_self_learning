"""Persona Anchor blueprint - metrics and injection history."""

from quart import Blueprint, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

anchor_bp = Blueprint("anchor", __name__, url_prefix="/api/anchor")


@anchor_bp.route("/metrics", methods=["GET"])
@require_auth
async def get_anchor_metrics():
    """Return Persona Anchor metrics and recent injection history."""
    try:
        container = get_container()
        hook_handler = getattr(container, "hook_handler", None)

        if hook_handler is None:
            return jsonify({
                "enabled": False,
                "reason": "hook_handler not initialized",
                "total_calls": 0,
                "successful_injections": 0,
                "injection_rate": 0.0,
                "skips_disabled": 0,
                "skips_insufficient": 0,
                "skips_no_scored": 0,
                "avg_bot_pool_size": 0.0,
                "avg_user_pool_size": 0.0,
                "avg_relevance_score": 0.0,
                "recent_history": [],
            }), 200

        metrics = hook_handler.persona_anchor_metrics
        if metrics is None:
            return jsonify({
                "enabled": False,
                "reason": "persona_anchor not initialized",
                "total_calls": 0,
                "successful_injections": 0,
                "injection_rate": 0.0,
                "skips_disabled": 0,
                "skips_insufficient": 0,
                "skips_no_scored": 0,
                "avg_bot_pool_size": 0.0,
                "avg_user_pool_size": 0.0,
                "avg_relevance_score": 0.0,
                "recent_history": [],
            }), 200

        return jsonify(metrics), 200

    except Exception as e:
        logger.error(f"[Anchor] Failed to get metrics: {e}")
        return error_response(str(e), 500)


@anchor_bp.route("/config", methods=["GET"])
@require_auth
async def get_anchor_config():
    """Return current Persona Anchor configuration."""
    try:
        container = get_container()
        config = getattr(container, "plugin_config", None)

        if config is None:
            return error_response("plugin_config not available", 500)

        return jsonify({
            "enable_persona_anchor": getattr(config, "enable_persona_anchor", False),
            "persona_anchor_bot_k": getattr(config, "persona_anchor_bot_k", 3),
            "persona_anchor_user_k": getattr(config, "persona_anchor_user_k", 2),
            "persona_anchor_pool": getattr(config, "persona_anchor_pool", 30),
            "persona_anchor_min_samples": getattr(config, "persona_anchor_min_samples", 3),
        }), 200

    except Exception as e:
        logger.error(f"[Anchor] Failed to get config: {e}")
        return error_response(str(e), 500)
