"""Database access layer -- managers and factory."""

from .sqlalchemy_database_manager import SQLAlchemyDatabaseManager
from .manager_factory import ManagerFactory, get_manager_factory

# 向后兼容别名：大量服务文件以 DatabaseManager 作为类型引用
DatabaseManager = SQLAlchemyDatabaseManager

__all__ = [
    "SQLAlchemyDatabaseManager",
    "DatabaseManager",
    "ManagerFactory",
    "get_manager_factory",
]
