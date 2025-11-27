"""
Quart 应用工厂
"""
import secrets
from quart import Quart
from quart_cors import cors
from astrbot.api import logger

from .config import WebUIConfig
from .middleware.error_handler import register_error_handlers


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

    # 配置密钥
    app.secret_key = secrets.token_hex(16)

    # 启用 CORS
    cors(app)

    # 存储配置到应用上下文
    if webui_config:
        app.config['WEBUI_CONFIG'] = webui_config

    # 注册错误处理
    register_error_handlers(app)

    logger.info("✅ [WebUI] Quart 应用创建成功")

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
        logger.info(f"✅ [WebUI] 已注册蓝图: {bp.name}")

    logger.info(f"✅ [WebUI] 共注册 {len(blueprints)} 个蓝图")
