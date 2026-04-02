"""
Quart 应用工厂
"""
import os
import secrets
from datetime import timedelta
from quart import Quart, redirect
from quart_cors import cors
from astrbot.api import logger

from .config import WebUIConfig
from .middleware.error_handler import register_error_handlers


def _get_or_create_secret_key(data_dir: str) -> str:
    """获取或创建持久化的 secret_key。

    首次运行时生成随机密钥并保存到磁盘，后续重启复用同一密钥，
    确保 session cookie 在服务器重启后仍然有效。
    """
    secret_file = os.path.join(data_dir, ".secret_key")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
        # 生成新密钥并持久化
        key = secrets.token_hex(32)
        os.makedirs(os.path.dirname(secret_file), exist_ok=True)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(key)
        logger.info(f" [WebUI] 已生成并保存新的 secret_key: {secret_file}")
        return key
    except Exception as e:
        logger.warning(f" [WebUI] 无法持久化 secret_key ({e})，将使用临时密钥")
        return secrets.token_hex(32)


def create_app(webui_config: WebUIConfig = None) -> Quart:
    """
    创建 Quart 应用

    Args:
        webui_config: WebUI 配置

    Returns:
        Quart 应用实例
    """
    # 创建应用
    app = Quart(
        __name__,
        static_folder=webui_config.static_dir if webui_config else None,
        static_url_path="/static",
        template_folder=webui_config.template_dir if webui_config else None
    )

    # 配置持久化密钥（跨重启保持 session 有效）
    if webui_config and webui_config.data_dir:
        app.secret_key = _get_or_create_secret_key(webui_config.data_dir)
    else:
        app.secret_key = secrets.token_hex(32)

    # Session 配置
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # 启用 CORS
    cors(app)

    # 存储配置到应用上下文
    if webui_config:
        app.config['WEBUI_CONFIG'] = webui_config

    # 注册错误处理
    register_error_handlers(app)

    # 根路由重定向到 /api/
    @app.route("/")
    async def root_redirect():
        return redirect("/api/")

    logger.info(" [WebUI] Quart 应用创建成功")

    return app


def register_blueprints(app: Quart):
    """
    注册所有蓝图

    Args:
        app: Quart 应用实例
    """
    from .blueprints import get_blueprints

    blueprints = get_blueprints()

    for bp in blueprints:
        app.register_blueprint(bp)
        logger.info(f" [WebUI] 已注册蓝图: {bp.name}")

    logger.info(f" [WebUI] 共注册 {len(blueprints)} 个蓝图")
