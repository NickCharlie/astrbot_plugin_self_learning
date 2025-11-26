"""
数据库后端抽象接口 - 定义统一的数据库操作接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio


class DatabaseType(Enum):
    """数据库类型枚举"""
    SQLITE = "sqlite"
    MYSQL = "mysql"


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_type: DatabaseType

    # SQLite 配置
    sqlite_path: Optional[str] = None

    # MySQL 配置
    mysql_host: Optional[str] = None
    mysql_port: int = 3306
    mysql_user: Optional[str] = None
    mysql_password: Optional[str] = None
    mysql_database: Optional[str] = None
    mysql_charset: str = "utf8mb4"

    # 连接池配置
    max_connections: int = 10
    min_connections: int = 2
    connection_timeout: int = 30

    def validate(self) -> Tuple[bool, Optional[str]]:
        """验证配置是否有效"""
        if self.db_type == DatabaseType.SQLITE:
            if not self.sqlite_path:
                return False, "SQLite path is required"
        elif self.db_type == DatabaseType.MYSQL:
            if not all([self.mysql_host, self.mysql_user, self.mysql_database]):
                return False, "MySQL host, user, and database are required"
        else:
            return False, f"Unsupported database type: {self.db_type}"

        return True, None


class ConnectionPool(ABC):
    """数据库连接池抽象基类"""

    @abstractmethod
    async def initialize(self):
        """初始化连接池"""
        pass

    @abstractmethod
    async def get_connection(self):
        """获取数据库连接"""
        pass

    @abstractmethod
    async def return_connection(self, conn):
        """归还数据库连接"""
        pass

    @abstractmethod
    async def close_all(self):
        """关闭所有连接"""
        pass


class IDatabaseBackend(ABC):
    """数据库后端接口"""

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化数据库连接"""
        pass

    @abstractmethod
    async def close(self) -> bool:
        """关闭数据库连接"""
        pass

    @abstractmethod
    async def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """
        执行SQL语句（INSERT, UPDATE, DELETE）

        Args:
            sql: SQL语句
            params: SQL参数

        Returns:
            影响的行数
        """
        pass

    @abstractmethod
    async def execute_many(self, sql: str, params_list: List[Tuple]) -> int:
        """
        批量执行SQL语句

        Args:
            sql: SQL语句
            params_list: 参数列表

        Returns:
            影响的总行数
        """
        pass

    @abstractmethod
    async def fetch_one(self, sql: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
        """
        查询单行数据

        Args:
            sql: SQL语句
            params: SQL参数

        Returns:
            查询结果（单行）或 None
        """
        pass

    @abstractmethod
    async def fetch_all(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """
        查询所有数据

        Args:
            sql: SQL语句
            params: SQL参数

        Returns:
            查询结果列表
        """
        pass

    @abstractmethod
    async def begin_transaction(self):
        """开始事务"""
        pass

    @abstractmethod
    async def commit(self):
        """提交事务"""
        pass

    @abstractmethod
    async def rollback(self):
        """回滚事务"""
        pass

    @abstractmethod
    async def create_table(self, table_name: str, schema: str) -> bool:
        """
        创建表

        Args:
            table_name: 表名
            schema: 表结构SQL（DDL）

        Returns:
            是否创建成功
        """
        pass

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在

        Args:
            table_name: 表名

        Returns:
            表是否存在
        """
        pass

    @abstractmethod
    async def get_table_list(self) -> List[str]:
        """
        获取所有表名列表

        Returns:
            表名列表
        """
        pass

    @abstractmethod
    async def export_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """
        导出表数据

        Args:
            table_name: 表名

        Returns:
            表数据列表（字典格式）
        """
        pass

    @abstractmethod
    async def import_table_data(self, table_name: str, data: List[Dict[str, Any]]) -> int:
        """
        导入表数据

        Args:
            table_name: 表名
            data: 数据列表（字典格式）

        Returns:
            导入的行数
        """
        pass

    @abstractmethod
    def get_connection_context(self):
        """
        获取连接上下文管理器

        Returns:
            异步上下文管理器
        """
        pass

    @property
    @abstractmethod
    def db_type(self) -> DatabaseType:
        """获取数据库类型"""
        pass

    @abstractmethod
    def convert_ddl(self, sqlite_ddl: str) -> str:
        """
        转换DDL语句（SQLite -> 目标数据库）

        Args:
            sqlite_ddl: SQLite DDL语句

        Returns:
            转换后的DDL语句
        """
        pass
