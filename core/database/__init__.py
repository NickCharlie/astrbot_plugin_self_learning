"""
数据库后端模块 - 支持 SQLite 和 MySQL
"""
from .backend_interface import IDatabaseBackend, DatabaseConfig, ConnectionPool, DatabaseType
from .sqlite_backend import SQLiteBackend
from .mysql_backend import MySQLBackend
from .factory import DatabaseFactory

__all__ = [
    'IDatabaseBackend',
    'DatabaseConfig',
    'ConnectionPool',
    'DatabaseType',
    'SQLiteBackend',
    'MySQLBackend',
    'DatabaseFactory'
]
