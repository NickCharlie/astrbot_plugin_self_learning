"""
错误处理中间件
"""
from quart import Quart
from ..utils.response import error_response
from astrbot.api import logger


def register_error_handlers(app: Quart):
    """注册错误处理器"""

    @app.errorhandler(404)
    async def not_found(error):
        return error_response('资源不存在', 404)

    @app.errorhandler(500)
    async def internal_error(error):
        logger.error(f"服务器内部错误: {error}", exc_info=True)
        return error_response('服务器内部错误', 500)

    @app.errorhandler(Exception)
    async def handle_exception(error):
        logger.error(f"未捕获的异常: {error}", exc_info=True)
        return error_response(f'服务器错误: {str(error)}', 500)
