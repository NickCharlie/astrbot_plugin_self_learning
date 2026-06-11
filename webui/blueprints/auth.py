"""
认证蓝图 - WebUI 免密访问，可选启用登录密码
"""
import os
from quart import Blueprint, render_template, jsonify, redirect, request, session, url_for
from astrbot.api import logger

from ..dependencies import get_container
from ..middleware.auth import is_authenticated, require_auth
from ..services.auth_service import AuthService
from ..utils.response import error_response

_TEMPLATE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'web_res', 'static', 'html')
)

auth_bp = Blueprint('auth', __name__, url_prefix='/api', template_folder=_TEMPLATE_DIR)


@auth_bp.route("/")
@require_auth
async def read_root():
    """根目录 - 渲染监控板。"""
    return await render_template("dashboard.html")


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
    return await render_template("dashboard.html")


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
