"""
错误处理中间件 — FastAPI 异常处理器
"""
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from astrbot.api import logger

from ..compat import jsonify


def register_error_handlers(app):
    """注册错误处理器（app 为兼容层应用实例）"""

    fastapi_app = app.fastapi_app

    @fastapi_app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            message = "资源不存在"
        elif exc.status_code >= 500:
            message = "服务器内部错误"
        else:
            message = str(getattr(exc, "detail", "请求错误"))
        return jsonify(
            {"success": False, "message": message}, status_code=exc.status_code
        )

    @fastapi_app.exception_handler(Exception)
    async def handle_exception(request, exc: Exception):
        logger.error(f"未捕获的异常: {exc}", exc_info=True)
        # 兜底响应不回显异常文本（可能含内部路径/SQL 片段），详情只进日志
        return JSONResponse(
            {"success": False, "message": "服务器内部错误，请稍后重试"},
            status_code=500,
        )
