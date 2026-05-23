"""Integration blueprint for companion plugin dashboards."""

from quart import Blueprint, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..services.integration_service import IntegrationService
from ..utils.response import error_response

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api")


@integrations_bp.route("/integrations/status", methods=["GET"])
@require_auth
async def get_integrations_status():
    """Return runtime delegation and companion dashboard links."""
    try:
        service = IntegrationService(get_container())
        return jsonify(service.get_status()), 200
    except Exception as e:
        logger.error(f"获取功能融合状态失败: {e}", exc_info=True)
        return error_response(f"获取功能融合状态失败: {str(e)}", 500)
