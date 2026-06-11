"""
认证中间件
"""
from functools import wraps
from quart import jsonify, redirect, request, session, url_for

from ..dependencies import get_container


def _webui_password_enabled() -> bool:
    try:
        config = get_container().plugin_config
    except Exception:
        return False
    return getattr(config, "enable_webui_password", False) is True


def require_auth(f):
    """要求认证；未开启 WebUI 密码时保持免密兼容。"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not _webui_password_enabled():
            return await f(*args, **kwargs)
        if session.get("authenticated"):
            return await f(*args, **kwargs)
        if request.method == "GET" and request.path in {"/api/", "/api/index"}:
            return redirect(url_for("auth.login_page"))
        return jsonify({
            "error": "未认证，请先登录",
            "redirect": "/api/login",
        }), 401
    return decorated_function


def is_authenticated() -> bool:
    """检查是否已认证；免密模式始终视为已认证。"""
    if not _webui_password_enabled():
        return True
    return bool(session.get("authenticated"))
