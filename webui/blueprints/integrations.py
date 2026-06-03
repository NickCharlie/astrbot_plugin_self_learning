"""Integration blueprint for companion plugin dashboards."""

from html import escape

from quart import Blueprint, Response, jsonify, redirect
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


@integrations_bp.route(
    "/plugin/page/content/<plugin_name>/<page_name>/",
    defaults={"asset_path": ""},
    methods=["GET"],
)
@integrations_bp.route(
    "/plugin/page/content/<plugin_name>/<page_name>/<path:asset_path>",
    methods=["GET"],
)
@require_auth
async def redirect_companion_plugin_page(
    plugin_name: str,
    page_name: str,
    asset_path: str,
):
    """Redirect known companion plugin Page URLs to AstrBot Dashboard."""
    try:
        service = IntegrationService(get_container())
        target_url = service.get_plugin_page_url(plugin_name, page_name, asset_path)
        if not target_url:
            return error_response("该插件页面需要在 AstrBot Dashboard 中打开。", 404)
        return redirect(target_url)
    except Exception as e:
        logger.error(f"获取伴随插件 AstrBot 页面失败: {e}", exc_info=True)
        return error_response(f"获取伴随插件 AstrBot 页面失败: {str(e)}", 500)


def _render_embed_shell(target: dict) -> str:
    title = escape(str(target.get("title") or "伴随插件面板"))
    role = escape(str(target.get("role") or ""))
    target_url = target.get("target_url") or ""
    escaped_url = escape(str(target_url), quote=True)
    open_url = target.get("open_url") or target_url
    escaped_open_url = escape(str(open_url), quote=True)
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
        f'<a class="button primary" href="{escaped_open_url}" target="_blank" rel="noopener noreferrer">新窗口打开</a>'
        if open_url
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
