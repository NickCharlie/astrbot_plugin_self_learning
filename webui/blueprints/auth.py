"""
认证蓝图 - WebUI 免密访问
"""
import os
from quart import Blueprint, render_template, jsonify, redirect, url_for
from astrbot.api import logger

from ..middleware.auth import require_auth
from ..utils.response import error_response

_TEMPLATE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'web_res', 'static', 'html')
)

auth_bp = Blueprint('auth', __name__, url_prefix='/api', template_folder=_TEMPLATE_DIR)


@auth_bp.route("/")
async def read_root():
    """根目录 - 免密渲染监控板。"""
    return await render_template("dashboard.html")


@auth_bp.route("/login", methods=["GET"])
async def login_page():
    """兼容旧入口：直接进入主界面。"""
    return redirect(url_for('auth.read_root_index'))


@auth_bp.route("/login", methods=["POST"])
async def login():
    """兼容旧接口：免密模式下直接返回成功。"""
    try:
        return jsonify({
            "message": "Passwordless WebUI access granted",
            "must_change": False,
            "redirect": "/api/index"
        }), 200
    except Exception as e:
        logger.error(f"登录处理失败: {e}", exc_info=True)
        return error_response(f"登录失败: {str(e)}", 500)


@auth_bp.route("/index")
async def read_root_index():
    """主页面 - 免密渲染监控板。"""
    return await render_template("dashboard.html")


@auth_bp.route("/plugin_change_password", methods=["GET"])
async def change_password_page():
    """免密模式下不再提供修改密码页面。"""
    return redirect(url_for('auth.read_root_index'))


@auth_bp.route("/plugin_change_password", methods=["POST"])
async def change_password():
    """免密模式下禁用修改密码接口。"""
    try:
        return jsonify({
            "success": False,
            "error": "WebUI 已启用免密访问，无需修改密码",
            "redirect": "/api/index"
        }), 410
    except Exception as e:
        logger.error(f"修改密码失败: {e}", exc_info=True)
        return error_response(f"修改密码失败: {str(e)}", 500)


@auth_bp.route("/logout", methods=["POST"])
@require_auth
async def logout():
    """免密模式下登出为兼容性 no-op。"""
    try:
        return jsonify({
            "message": "Passwordless WebUI stays open",
            "redirect": "/api/index"
        }), 200
    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return error_response(f"登出失败: {str(e)}", 500)
