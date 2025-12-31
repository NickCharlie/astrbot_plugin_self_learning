"""
数据库管理器工厂
默认使用 SQLAlchemy ORM 数据库管理器（支持自动迁移）
"""
from astrbot.api import logger

from ..config import PluginConfig
from .sqlalchemy_database_manager import SQLAlchemyDatabaseManager


def create_database_manager(
    config: PluginConfig,
    context=None
) -> SQLAlchemyDatabaseManager:
    """
    创建数据库管理器

    默认使用 SQLAlchemy 版本（带自动数据库迁移功能）

    Args:
        config: 插件配置
        context: 上下文（可选）

    Returns:
        SQLAlchemy 数据库管理器实例
    """
    logger.info("📦 [数据库] 使用 SQLAlchemy 版本的数据库管理器（支持自动迁移）")
    return SQLAlchemyDatabaseManager(config, context)


__all__ = [
    'SQLAlchemyDatabaseManager',
    'create_database_manager',
]
