"""Integration blueprint for companion plugin dashboards."""

from html import escape

from quart import Blueprint, Response, jsonify, request
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
    """Return runtime delegation and companion dashboard links."""
    try:
        service = IntegrationService(get_container())
        return jsonify(service.get_status()), 200
    except Exception as e:
        logger.error(f"获取功能融合状态失败: {e}", exc_info=True)
        return error_response(f"获取功能融合状态失败: {str(e)}", 500)


@integrations_bp.route("/integrations/embed/<plugin_id>", methods=["GET"])
@require_auth
async def embed_integration_dashboard(plugin_id: str):
    """Render a same-origin shell for a companion plugin WebUI."""
    try:
        service = IntegrationService(get_container())
        target = service.get_embed_target(plugin_id)
        html = _render_embed_shell(target)
        return Response(
            html,
            mimetype="text/html",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        logger.error(f"获取伴随插件嵌入页失败: {e}", exc_info=True)
        return error_response(f"获取伴随插件嵌入页失败: {str(e)}", 500)


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
        return error_response(f"预览 MaiBot 学习数据失败: {str(e)}", 500)


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
        return error_response(f"导入 MaiBot 学习数据失败: {str(e)}", 500)


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
        return error_response(f"导出 MaiBot 学习数据失败: {str(e)}", 500)


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
        return error_response(f"预览 SillyTavern 世界书失败: {str(e)}", 500)


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
        return error_response(f"导入 SillyTavern 世界书失败: {str(e)}", 500)


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
        return error_response(f"读取 SillyTavern 世界书导入历史失败: {str(e)}", 500)


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
        return error_response(f"预览 QQ 聊天记录失败: {str(e)}", 500)


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
        return error_response(f"导入 QQ 聊天记录失败: {str(e)}", 500)


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


def _render_embed_shell(target: dict) -> str:
    title = escape(str(target.get("title") or "伴随插件面板"))
    role = escape(str(target.get("role") or ""))
    target_url = target.get("target_url") or ""
    escaped_url = escape(str(target_url), quote=True)
    message = escape(str(target.get("message") or ""))
    active_label = "已加载" if target.get("active") else "未加载"
    delegated = target.get("delegated")
    delegated_label = (
        ""
        if delegated is None
        else ("已委托" if delegated else "本地回退")
    )
    chips = "".join(
        f"<span>{escape(label)}</span>"
        for label in [active_label, delegated_label, str(target.get("kind") or "panel")]
        if label
    )
    iframe = (
        f'<iframe title="{title}" src="{escaped_url}" loading="eager" referrerpolicy="no-referrer"></iframe>'
        if target.get("available") and target_url
        else f'<div class="empty"><strong>面板不可用</strong><p>{message}</p></div>'
    )
    open_action = (
        f'<a class="button primary" href="{escaped_url}" target="_blank" rel="noopener noreferrer">新窗口打开</a>'
        if target_url
        else ""
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #182230;
      --muted: #667085;
      --border: #d9e0ea;
      --accent: #2563eb;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f172a;
        --panel: #111827;
        --text: #e5edf8;
        --muted: #9aa7b8;
        --border: #243044;
        --accent: #60a5fa;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      min-height: 100%;
      display: grid;
      grid-template-rows: auto 1fr;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }}
    h1 {{ margin: 0; font-size: 15px; line-height: 1.25; }}
    p {{ margin: 3px 0 0; color: var(--muted); font-size: 12px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
    .meta span {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
    .button {{
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0 10px;
      color: var(--text);
      background: transparent;
      text-decoration: none;
      font-size: 13px;
      white-space: nowrap;
    }}
    .button.primary {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    main {{
      min-height: 0;
      padding: 10px;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      min-height: 560px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
    }}
    .empty {{
      min-height: 360px;
      display: grid;
      place-items: center;
      text-align: center;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      padding: 24px;
    }}
    .empty strong {{ display: block; margin-bottom: 6px; }}
    @media (max-width: 720px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .actions {{ justify-content: flex-start; }}
      main {{ padding: 8px; }}
      iframe {{ min-height: 620px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{title}</h1>
      <p>{role}</p>
      <div class="meta">{chips}</div>
    </div>
    <div class="actions">
      {open_action}
      <a class="button" href="">刷新</a>
    </div>
  </header>
  <main>{iframe}</main>
</body>
</html>"""
