"""Integration blueprint for companion plugin dashboards."""

from ..compat import Blueprint, jsonify, request
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..services.integration_service import IntegrationService
from ..utils.response import error_response
try:
    from ...services.integration.maibot_learning_importer import MaiBotLearningImporter
    from ...services.integration.qq_chat_history_importer import QQChatHistoryImporter
    from ...services.integration.worldbook_importer import WorldBookImporter
except ImportError:
    from services.integration.maibot_learning_importer import MaiBotLearningImporter
    from services.integration.qq_chat_history_importer import QQChatHistoryImporter
    from services.integration.worldbook_importer import WorldBookImporter

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api")


@integrations_bp.route("/integrations/status", methods=["GET"])
@require_auth
async def get_integrations_status():
    """Return runtime delegation and companion dashboard status."""
    try:
        service = IntegrationService(get_container())
        return jsonify(await service.get_status()), 200
    except Exception as e:
        logger.error(f"获取功能融合状态失败: {e}", exc_info=True)
        return error_response("获取功能融合状态失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/maibot-learning/preview", methods=["POST"])
@require_auth
async def preview_maibot_learning():
    """Preview MaiBot learning data before importing it."""
    try:
        body = await request.get_json(silent=True) or {}
        importer = MaiBotLearningImporter()
        return jsonify({
            "success": True,
            "data": importer.preview(**_maibot_source_args(body)),
        }), 200
    except Exception as e:
        logger.error(f"预览 MaiBot 学习数据失败: {e}", exc_info=True)
        return error_response("预览 MaiBot 学习数据失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/maibot-learning/import", methods=["POST"])
@require_auth
async def import_maibot_learning():
    """Import MaiBot learning data into this plugin."""
    try:
        body = await request.get_json(silent=True) or {}
        container = get_container()
        database_manager = getattr(container, "database_manager", None)
        importer = MaiBotLearningImporter(database_manager)
        result = await importer.import_from_source(
            **_maibot_source_args(body),
            default_group_id=body.get("default_group_id") or "global",
            import_expressions=_body_bool(body, "import_expressions", True),
            import_jargons=_body_bool(body, "import_jargons", True),
            import_memories=_body_bool(body, "import_memories", True),
            approve_checked_expressions=_body_bool(body, "approve_checked_expressions", True),
        )
        return jsonify({"success": bool(result.get("success")), "data": result}), 200
    except Exception as e:
        logger.error(f"导入 MaiBot 学习数据失败: {e}", exc_info=True)
        return error_response("导入 MaiBot 学习数据失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/maibot-learning/export", methods=["POST"])
@require_auth
async def export_maibot_learning():
    """Export MaiBot learning data as a normalized JSON package."""
    try:
        body = await request.get_json(silent=True) or {}
        importer = MaiBotLearningImporter()
        return jsonify({
            "success": True,
            "data": importer.export_json(**_maibot_source_args(body)),
        }), 200
    except Exception as e:
        logger.error(f"导出 MaiBot 学习数据失败: {e}", exc_info=True)
        return error_response("导出 MaiBot 学习数据失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/worldbook/preview", methods=["POST"])
@require_auth
async def preview_worldbook():
    """Preview SillyTavern worldbook JSON before importing it."""
    try:
        body = await request.get_json(silent=True) or {}
        importer = WorldBookImporter()
        return jsonify({
            "success": True,
            "data": importer.preview(**_worldbook_source_args(body)),
        }), 200
    except Exception as e:
        logger.error(f"预览 SillyTavern 世界书失败: {e}", exc_info=True)
        return error_response("预览 SillyTavern 世界书失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/worldbook/import", methods=["POST"])
@require_auth
async def import_worldbook():
    """Import SillyTavern worldbook entries into this plugin."""
    try:
        body = await request.get_json(silent=True) or {}
        container = get_container()
        database_manager = getattr(container, "database_manager", None)
        importer = WorldBookImporter(database_manager)
        result = await importer.import_from_source(
            **_worldbook_source_args(body),
            default_group_id=body.get("default_group_id") or body.get("group_id") or "global",
            import_memories=_body_bool(body, "import_memories", True),
            import_jargons=_body_bool(body, "import_jargons", True),
            import_knowledge_graph=_body_bool(body, "import_knowledge_graph", True),
            include_disabled=_body_bool(body, "include_disabled", False),
        )
        return jsonify({"success": bool(result.get("success")), "data": result}), 200
    except Exception as e:
        logger.error(f"导入 SillyTavern 世界书失败: {e}", exc_info=True)
        return error_response("导入 SillyTavern 世界书失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/worldbook/imports", methods=["GET"])
@require_auth
async def list_worldbook_imports():
    """List recent worldbook imports derived from review metadata."""
    try:
        container = get_container()
        database_manager = getattr(container, "database_manager", None)
        importer = WorldBookImporter(database_manager)
        data = await importer.import_history(
            limit=_query_int("limit", 20),
            offset=_query_int("offset", 0),
        )
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        logger.error(f"读取 SillyTavern 世界书导入历史失败: {e}", exc_info=True)
        return error_response("读取 SillyTavern 世界书导入历史失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/qq-chat-history/preview", methods=["POST"])
@require_auth
async def preview_qq_chat_history():
    """Preview QQ/QCE chat history before importing it."""
    try:
        body = await request.get_json(silent=True) or {}
        importer = QQChatHistoryImporter()
        data = importer.preview(
            **_qq_chat_source_args(body),
            default_group_id=body.get("default_group_id") or body.get("group_id") or "",
            include_training_pairs=_body_bool(body, "include_training_pairs", False),
            max_messages=_query_body_int(body, "max_messages", 100000),
            min_text_length=_query_body_int(body, "min_text_length", 2),
        )
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        logger.error(f"预览 QQ 聊天记录失败: {e}", exc_info=True)
        return error_response("预览 QQ 聊天记录失败: 请稍后重试", 500)


@integrations_bp.route("/integrations/qq-chat-history/import", methods=["POST"])
@require_auth
async def import_qq_chat_history():
    """Import QQ/QCE chat history into raw message learning data."""
    try:
        body = await request.get_json(silent=True) or {}
        container = get_container()
        database_manager = getattr(container, "database_manager", None)
        importer = QQChatHistoryImporter(database_manager)
        result = await importer.import_from_source(
            **_qq_chat_source_args(body),
            default_group_id=body.get("default_group_id") or body.get("group_id") or "",
            include_training_pairs=_body_bool(body, "include_training_pairs", False),
            max_messages=_query_body_int(body, "max_messages", 100000),
            min_text_length=_query_body_int(body, "min_text_length", 2),
        )
        return jsonify({"success": bool(result.get("success")), "data": result}), 200
    except Exception as e:
        logger.error(f"导入 QQ 聊天记录失败: {e}", exc_info=True)
        return error_response("导入 QQ 聊天记录失败: 请稍后重试", 500)


def _maibot_source_args(body: dict) -> dict:
    payload = body.get("payload")
    return {
        "maibot_root": body.get("maibot_root") or None,
        "db_path": body.get("db_path") or body.get("maibot_db_path") or None,
        "memorix_db_path": body.get("memorix_db_path") or None,
        "payload": payload if isinstance(payload, dict) else None,
    }


def _worldbook_source_args(body: dict) -> dict:
    payload = body.get("payload")
    if payload is None:
        payload = body.get("worldbook")
    return {
        "payload": payload if isinstance(payload, (dict, list, str)) else None,
        "json_text": body.get("json_text") or None,
        # Do not accept server-side paths from WebUI requests.  Callers should
        # upload/send JSON content instead; direct Python callers may still use
        # WorldBookImporter.load_package(json_path=...).
        "json_path": None,
    }


def _qq_chat_source_args(body: dict) -> dict:
    payload = body.get("payload")
    return {
        "source_path": body.get("source_path") or body.get("path") or body.get("qq_history_path") or None,
        "payload": payload if isinstance(payload, (dict, list, str)) else None,
        "json_text": body.get("json_text") or None,
    }


def _body_bool(body: dict, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _query_body_int(body: dict, key: str, default: int) -> int:
    try:
        value = int(body.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _query_int(key: str, default: int) -> int:
    try:
        return int(request.args.get(key, default))
    except (TypeError, ValueError):
        return default
