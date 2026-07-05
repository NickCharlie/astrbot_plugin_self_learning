"""
认证蓝图 - WebUI 免密访问，可选启用登录密码
"""
import os
from quart import Blueprint, render_template, jsonify, redirect, request, session, url_for, send_file
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import is_authenticated, require_auth
from ..services.auth_service import AuthService
from ..utils.response import add_no_store_headers, error_response

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_TEMPLATE_DIR = os.path.join(_PLUGIN_ROOT, 'web_res', 'static', 'html')

# 新版 Solid.js Dashboard 的 SPA 入口（由 web_src 构建产物部署到 web_res/static/dashboard）。
_DASHBOARD_SPA = os.path.join(_PLUGIN_ROOT, 'web_res', 'static', 'dashboard', 'index.html')


async def _render_dashboard():
    """渲染监控板入口（新版 Solid.js SPA）。

    新 SPA 为唯一入口；若构建产物缺失，返回带构建指引的 503 页面，
    而不是回退已移除的旧版单体 dashboard.html。
    """
    try:
        from ..frontend_builder import dashboard_artifact_exists
        dashboard_ready = dashboard_artifact_exists(_PLUGIN_ROOT)
    except Exception:
        dashboard_ready = os.path.exists(_DASHBOARD_SPA)

    if dashboard_ready:
        return await send_file(_DASHBOARD_SPA)
    logger.error(f"[WebUI] Dashboard SPA 入口缺失：{_DASHBOARD_SPA}")
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta http-equiv=\"refresh\" content=\"15\">"
        "<title>监控板构建中</title></head>"
        "<body style=\"font-family:system-ui,sans-serif;max-width:640px;margin:4rem auto;padding:0 1rem\">"
        "<h2>监控板前端正在准备中…</h2>"
        "<p>插件加载时已检测到前端产物缺失并尝试 <strong>后台自动构建</strong>，"
        "本页每 15 秒自动刷新。</p>"
        "<p>若较长时间后仍停留在此页，说明当前环境未安装 <code>Node.js</code> 或自动构建失败。"
        "可在插件根目录的 <code>web_src</code> 下手动执行 "
        "<code>pnpm install &amp;&amp; pnpm build</code>（或 <code>npm install &amp;&amp; npm run build</code>），"
        "产物会自动部署到 <code>web_res/static/dashboard</code>。</p>"
        "</body></html>",
        503,
    )


auth_bp = Blueprint('auth', __name__, url_prefix='/api', template_folder=_TEMPLATE_DIR)


@auth_bp.after_request
async def _disable_auth_response_cache(response):
    return add_no_store_headers(response)


@auth_bp.route("/")
@require_auth
async def read_root():
    """根目录 - 渲染监控板。"""
    return await _render_dashboard()


@auth_bp.route("/login", methods=["GET"])
async def login_page():
    """显示登录页面；免密模式下直接进入主界面。"""
    auth_service = AuthService(get_container())
    if not auth_service.is_password_enabled() or is_authenticated():
        return redirect(url_for('auth.read_root_index'))
    return await render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
async def login():
    """处理登录请求。"""
    try:
        data = await request.get_json(silent=True) or {}
        password = data.get("password", "")
        client_ip = request.remote_addr or "unknown"

        auth_service = AuthService(get_container())
        success, message, extra_data = await auth_service.login(password, client_ip)
        extra_data = extra_data or {}

        if success:
            if auth_service.is_password_enabled():
                session["authenticated"] = True
                session["must_change"] = bool(extra_data.get("must_change", False))
                session.permanent = True
            return jsonify({
                "message": message,
                "must_change": extra_data.get("must_change", False),
                "redirect": extra_data.get("redirect", "/api/index"),
            }), 200

        response_data = {"error": message}
        response_data.update(extra_data)
        status_code = 429 if extra_data.get("locked") else 401
        return jsonify(response_data), status_code
    except Exception as e:
        logger.error(f"登录处理失败: {e}", exc_info=True)
        return error_response(f"登录失败: {str(e)}", 500)


@auth_bp.route("/index")
@require_auth
async def read_root_index():
    """主页面 - 渲染监控板。"""
    auth_service = AuthService(get_container())
    if auth_service.is_password_enabled() and auth_service.check_must_change_password():
        return redirect(url_for('auth.change_password_page'))
    return await _render_dashboard()


@auth_bp.route("/plugin_change_password", methods=["GET"])
@require_auth
async def change_password_page():
    """显示修改密码页面。"""
    auth_service = AuthService(get_container())
    if not auth_service.is_password_enabled():
        return redirect(url_for('auth.read_root_index'))
    return await render_template("change_password.html")


@auth_bp.route("/plugin_change_password", methods=["POST"])
@require_auth
async def change_password():
    """处理修改密码请求。"""
    try:
        auth_service = AuthService(get_container())
        if not auth_service.is_password_enabled():
            return jsonify({
                "success": False,
                "error": "WebUI 已启用免密访问，无需修改密码",
                "redirect": "/api/index"
            }), 410

        data = await request.get_json(silent=True) or {}
        success, message = await auth_service.change_password(
            data.get("old_password", ""),
            data.get("new_password", ""),
        )
        if success:
            session["must_change"] = False
            return jsonify({
                "success": True,
                "message": message,
                "redirect": "/api/index",
            }), 200
        return jsonify({
            "success": False,
            "error": message,
        }), 400
    except Exception as e:
        logger.error(f"修改密码失败: {e}", exc_info=True)
        return error_response(f"修改密码失败: {str(e)}", 500)


@auth_bp.route("/logout", methods=["POST"])
@require_auth
async def logout():
    """处理登出。"""
    try:
        auth_service = AuthService(get_container())
        if auth_service.is_password_enabled():
            session.clear()
            return jsonify({
                "message": "Logged out successfully",
                "redirect": "/api/login"
            }), 200
        return jsonify({
            "message": "Passwordless WebUI stays open",
            "redirect": "/api/index"
        }), 200
    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return error_response(f"登出失败: {str(e)}", 500)
