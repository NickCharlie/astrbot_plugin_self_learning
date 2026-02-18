"""
WebUI 包 - 提供 Web 管理界面
"""
from .server import Server
from .dependencies import set_plugin_services

__all__ = ['Server', 'set_plugin_services']
