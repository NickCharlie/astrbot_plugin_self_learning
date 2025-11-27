"""
认证中间件
"""
from functools import wraps
from quart import session
from ..utils.response import error_response


def require_auth(f):
    """要求认证的装饰器"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return error_response('未认证，请先登录', 401)
        return await f(*args, **kwargs)
    return decorated_function


def is_authenticated() -> bool:
    """检查是否已认证"""
    return session.get('authenticated', False)
