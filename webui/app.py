"""
WebUI 应用工厂 — 基于 FastAPI 构建（与 AstrBot core v4.26+ 的 ASGI 栈对齐）。

``Quart``/``Blueprint`` 等符号来自 ``webui.compat`` 兼容层：既有蓝图的
处理器保持 Quart 风格不改写，运行时由 FastAPI/uvicorn 承载。
"""
import os
import secrets
from datetime import timedelta

from astrbot.api import logger

from .compat import CORSMiddleware, Quart, redirect
from .compat import _ResponseHeadersMiddleware as _HeaderMiddleware
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


def _enable_cors(app: Quart) -> None:
    """启用 CORS（与原 quart_cors 行为对齐，不携带凭据）。"""
    app.fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Self-Learning-Key",
        ],
    )


def _disable_dynamic_response_cache(app: Quart) -> None:
    """动态 WebUI/API 响应禁用缓存（静态资源除外）。"""
    app.fastapi_app.add_middleware(
        _HeaderMiddleware, skip_static=True, security_headers=False
    )


def _add_security_headers(app: Quart) -> None:
    """补充基础安全响应头（CSP 需 nonce 配合 SPA 内联样式，暂不启用）。"""
    app.fastapi_app.add_middleware(
        _HeaderMiddleware, skip_static=True, cache_headers=False
    )


def create_app(webui_config=None) -> Quart:
    """
    创建 WebUI 应用（FastAPI，经兼容层包装）

    Args:
        webui_config: WebUI 配置

    Returns:
        兼容层的应用实例
    """
    app = Quart(
        __name__,
        static_folder=webui_config.static_dir if webui_config else None,
        static_url_path="/static",
        template_folder=webui_config.template_dir if webui_config else None,
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
    _enable_cors(app)
    _disable_dynamic_response_cache(app)
    _add_security_headers(app)

    # 存储配置到应用上下文
    if webui_config:
        app.config['WEBUI_CONFIG'] = webui_config
        app.config['ENABLE_WEB_DEP_INSTALL'] = webui_config.enable_web_dependency_install
        app.config['ALLOWED_DEPENDENCY_PACKAGES'] = webui_config.allowed_dependency_packages

    # 注册错误处理
    register_error_handlers(app)

    # 根路由重定向到 /api/
    @app.route("/")
    async def root_redirect():
        return redirect("/api/")

    logger.info(" [WebUI] FastAPI 应用创建成功")

    return app


def register_blueprints(app: Quart):
    """
    注册所有蓝图

    Args:
        app: 兼容层应用实例
    """
    from .blueprints import get_blueprints

    blueprints = get_blueprints()

    for bp in blueprints:
        app.register_blueprint(bp)
        logger.info(f" [WebUI] 已注册蓝图: {bp.name}")

    logger.info(f" [WebUI] 共注册 {len(blueprints)} 个蓝图")
