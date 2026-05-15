"""
WebUI 包 - 提供 Web 管理界面
"""
from .dependencies import set_plugin_services

__all__ = ['Server', 'set_plugin_services']


def __getattr__(name):
    if name == "Server":
        from .server import Server

        return Server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
