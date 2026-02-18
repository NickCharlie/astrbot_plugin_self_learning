"""
认证蓝图 - 处理用户登录、登出、修改密码
"""
from quart import Blueprint, render_template, request, jsonify, session, redirect, url_for
from astrbot.api import logger

from ..dependencies import get_container
from ..services.auth_service import AuthService
from ..middleware.auth import require_auth, is_authenticated
from ..utils.response import success_response, error_response

auth_bp = Blueprint('auth', __name__, url_prefix='/api')


@auth_bp.route("/")
async def read_root():
    """根目录 - 渲染 MacOS UI（前端自行判断登录状态）"""
    return await render_template("macos.html")


@auth_bp.route("/login", methods=["GET"])
async def login_page():
    """登录页面 - 渲染 MacOS UI（前端 Login 组件处理登录）"""
    return await render_template("macos.html")


@auth_bp.route("/login", methods=["POST"])
async def login():
    """处理用户登录 - 支持MD5加密和暴力破解防护"""
    try:
        # 获取请求数据
        data = await request.get_json()
        password = data.get("password", "")
        client_ip = request.remote_addr or "unknown"

        # 使用服务层处理登录
        container = get_container()
        auth_service = AuthService(container)
        success, message, extra_data = await auth_service.login(password, client_ip)

        if success:
            # 设置会话认证状态
            session['authenticated'] = True
            session.permanent = True

            response_data = {
                "message": message,
                "must_change": extra_data.get("must_change", False),
                "redirect": extra_data.get("redirect", "/api/index")
            }
            return jsonify(response_data), 200
        else:
            # 登录失败
            error_data = {
                "error": message
            }

            # 如果有额外数据（如锁定信息），添加到响应
            if extra_data:
                error_data.update(extra_data)

            status_code = 429 if extra_data and extra_data.get("locked") else 401
            return jsonify(error_data), status_code

    except Exception as e:
        logger.error(f"登录处理失败: {e}", exc_info=True)
        return error_response(f"登录失败: {str(e)}", 500)


@auth_bp.route("/index")
async def read_root_index():
    """主页面 - 渲染 MacOS UI"""
    return await render_template("macos.html")


@auth_bp.route("/plugin_change_password", methods=["GET"])
async def change_password_page():
    """显示修改密码页面"""
    # 检查是否已认证
    if not is_authenticated():
        return redirect(url_for('auth.login_page'))

    return await render_template("change_password.html")


@auth_bp.route("/plugin_change_password", methods=["POST"])
async def change_password():
    """处理修改密码请求 - 支持MD5加密存储"""
    try:
        # 检查是否已认证
        if not is_authenticated():
            return jsonify({
                "error": "Authentication required",
                "redirect": "/api/login"
            }), 401

        # 获取请求数据
        data = await request.get_json()
        old_password = data.get("old_password", "")
        new_password = data.get("new_password", "")

        # 使用服务层处理密码修改
        container = get_container()
        auth_service = AuthService(container)
        success, message = await auth_service.change_password(old_password, new_password)

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        logger.error(f"修改密码失败: {e}", exc_info=True)
        return error_response(f"修改密码失败: {str(e)}", 500)


@auth_bp.route("/logout", methods=["POST"])
@require_auth
async def logout():
    """处理用户登出"""
    try:
        session.clear()
        return jsonify({
            "message": "Logged out successfully",
            "redirect": "/api/login"
        }), 200
    except Exception as e:
        logger.error(f"登出失败: {e}", exc_info=True)
        return error_response(f"登出失败: {str(e)}", 500)
