"""Database access layer -- managers and factory.

Keep the factory import lazy: MCP and tests often only need the SQLAlchemy
manager, while ``manager_factory`` pulls in AstrBot runtime event types.
"""

from .sqlalchemy_database_manager import SQLAlchemyDatabaseManager

# 向后兼容别名：大量服务文件以 DatabaseManager 作为类型引用
DatabaseManager = SQLAlchemyDatabaseManager

__all__ = [
    "SQLAlchemyDatabaseManager",
    "DatabaseManager",
    "ManagerFactory",
    "get_manager_factory",
]


def __getattr__(name):
    if name in {"ManagerFactory", "get_manager_factory"}:
        from .manager_factory import ManagerFactory, get_manager_factory

        globals()["ManagerFactory"] = ManagerFactory
        globals()["get_manager_factory"] = get_manager_factory
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
