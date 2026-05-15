"""
认证中间件
"""
from functools import wraps


def require_auth(f):
    """Pack 分支 WebUI 使用免密访问，认证装饰器直接放行。"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        return await f(*args, **kwargs)
    return decorated_function


def is_authenticated() -> bool:
    """Pack 分支 WebUI 始终视为已认证。"""
    return True
