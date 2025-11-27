"""
数据库管理器工厂
根据配置选择使用传统 DatabaseManager 或 SQLAlchemy 版本
"""
from typing import Union
from astrbot.api import logger

from ..config import PluginConfig
from .database_manager import DatabaseManager
from .sqlalchemy_database_manager import SQLAlchemyDatabaseManager


def create_database_manager(
    config: PluginConfig,
    context=None
) -> Union[DatabaseManager, SQLAlchemyDatabaseManager]:
    """
    创建数据库管理器

    根据配置决定使用哪个实现:
    - config.use_sqlalchemy = True: 使用新的 SQLAlchemy 版本
    - config.use_sqlalchemy = False (默认): 使用传统版本

    Args:
        config: 插件配置
        context: 上下文（可选）

    Returns:
        数据库管理器实例
    """
    use_sqlalchemy = getattr(config, 'use_sqlalchemy', False)

    if use_sqlalchemy:
        logger.info("📦 [数据库] 使用 SQLAlchemy 版本的数据库管理器")
        return SQLAlchemyDatabaseManager(config, context)
    else:
        logger.info("📦 [数据库] 使用传统版本的数据库管理器")
        return DatabaseManager(config, context)


__all__ = [
    'DatabaseManager',
    'SQLAlchemyDatabaseManager',
    'create_database_manager',
]
