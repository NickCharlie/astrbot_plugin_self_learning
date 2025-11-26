"""
MySQL 数据库后端实现
"""
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Callable, TypeVar
from contextlib import asynccontextmanager

try:
    import aiomysql
    AIOMYSQL_AVAILABLE = True
except ImportError:
    AIOMYSQL_AVAILABLE = False
    aiomysql = None

from astrbot.api import logger

from .backend_interface import (
    IDatabaseBackend,
    DatabaseType,
    DatabaseConfig,
    ConnectionPool
)

T = TypeVar('T')


async def retry_on_mysql_error(func: Callable[..., T], max_retries: int = 3, initial_delay: float = 0.1) -> T:
    """
    对 MySQL 数据库操作进行重试，处理临时性错误

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间（秒）

    Returns:
        函数执行结果
    """
    delay = initial_delay
    last_error = None

    # MySQL 可重试的错误码
    RETRYABLE_ERRORS = {
        1205,  # Lock wait timeout
        1213,  # Deadlock
        2013,  # Lost connection
        2006,  # MySQL server has gone away
    }

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            error_msg = str(e)

            # 检查是否是可重试的错误
            is_retryable = False
            if hasattr(e, 'args') and len(e.args) > 0:
                error_code = e.args[0] if isinstance(e.args[0], int) else None
                if error_code in RETRYABLE_ERRORS:
                    is_retryable = True

            # 也检查错误消息
            if any(keyword in error_msg.lower() for keyword in ['deadlock', 'lock wait', 'lost connection', 'gone away']):
                is_retryable = True

            if not is_retryable:
                # 不是可重试的错误，直接抛出
                raise

            last_error = e
            if attempt < max_retries:
                logger.warning(f"[MySQL] 遇到临时错误，第 {attempt + 1}/{max_retries} 次重试（延迟 {delay:.2f}s）: {error_msg}")
                await asyncio.sleep(delay)
                delay *= 2  # 指数退避
            else:
                logger.error(f"[MySQL] 重试 {max_retries} 次后仍失败: {error_msg}")

    # 所有重试都失败
    raise last_error


class MySQLConnectionPool(ConnectionPool):
    """MySQL连接池"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[aiomysql.Pool] = None

    async def initialize(self):
        """初始化连接池"""
        if not AIOMYSQL_AVAILABLE:
            raise ImportError("aiomysql is not installed. Please install it: pip install aiomysql")

        self.pool = await aiomysql.create_pool(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            db=self.config.mysql_database,
            charset=self.config.mysql_charset,
            minsize=self.config.min_connections,
            maxsize=self.config.max_connections,
            autocommit=False
        )
        logger.info(f"[MySQL] 连接池初始化成功: {self.config.mysql_host}:{self.config.mysql_port}/{self.config.mysql_database}")

    async def get_connection(self):
        """获取数据库连接"""
        return await self.pool.acquire()

    async def return_connection(self, conn):
        """归还数据库连接"""
        if conn:
            self.pool.release(conn)

    async def close_all(self):
        """关闭所有连接"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("[MySQL] 连接池已关闭")


class MySQLBackend(IDatabaseBackend):
    """MySQL数据库后端实现"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection_pool: Optional[MySQLConnectionPool] = None
        self._current_transaction_conn: Optional[aiomysql.Connection] = None

    async def initialize(self) -> bool:
        """初始化数据库连接"""
        try:
            if not AIOMYSQL_AVAILABLE:
                logger.error("[MySQL] aiomysql未安装，请运行: pip install aiomysql")
                return False

            valid, error = self.config.validate()
            if not valid:
                logger.error(f"[MySQL] 配置验证失败: {error}")
                return False

            self.connection_pool = MySQLConnectionPool(self.config)
            await self.connection_pool.initialize()
            logger.info("[MySQL] 数据库初始化成功")
            return True
        except Exception as e:
            logger.error(f"[MySQL] 初始化失败: {e}", exc_info=True)
            return False

    async def close(self) -> bool:
        """关闭数据库连接"""
        try:
            if self.connection_pool:
                await self.connection_pool.close_all()
            logger.info("[MySQL] 数据库连接已关闭")
            return True
        except Exception as e:
            logger.error(f"[MySQL] 关闭失败: {e}", exc_info=True)
            return False

    async def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """执行SQL语句（带重试机制）"""
        async def _do_execute():
            async with self.get_connection_context() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, params or ())
                    await conn.commit()
                    return cursor.rowcount
        return await retry_on_mysql_error(_do_execute, max_retries=3)

    async def execute_many(self, sql: str, params_list: List[Tuple]) -> int:
        """批量执行SQL语句（带重试机制）"""
        async def _do_execute_many():
            async with self.get_connection_context() as conn:
                async with conn.cursor() as cursor:
                    await cursor.executemany(sql, params_list)
                    await conn.commit()
                    return cursor.rowcount
        return await retry_on_mysql_error(_do_execute_many, max_retries=3)

    async def fetch_one(self, sql: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
        """查询单行数据（带重试机制）"""
        async def _do_fetch_one():
            async with self.get_connection_context() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, params or ())
                    return await cursor.fetchone()
        return await retry_on_mysql_error(_do_fetch_one, max_retries=2)

    async def fetch_all(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """查询所有数据（带重试机制）"""
        async def _do_fetch_all():
            async with self.get_connection_context() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, params or ())
                    return await cursor.fetchall()
        return await retry_on_mysql_error(_do_fetch_all, max_retries=2)

    async def begin_transaction(self):
        """开始事务"""
        if self._current_transaction_conn is None:
            self._current_transaction_conn = await self.connection_pool.get_connection()
        await self._current_transaction_conn.begin()

    async def commit(self):
        """提交事务"""
        if self._current_transaction_conn:
            await self._current_transaction_conn.commit()
            await self.connection_pool.return_connection(self._current_transaction_conn)
            self._current_transaction_conn = None

    async def rollback(self):
        """回滚事务"""
        if self._current_transaction_conn:
            await self._current_transaction_conn.rollback()
            await self.connection_pool.return_connection(self._current_transaction_conn)
            self._current_transaction_conn = None

    async def create_table(self, table_name: str, schema: str) -> bool:
        """创建表"""
        try:
            # 转换SQLite DDL到MySQL DDL
            mysql_schema = self.convert_ddl(schema)
            await self.execute(mysql_schema)
            logger.info(f"[MySQL] 创建表成功: {table_name}")
            return True
        except Exception as e:
            logger.error(f"[MySQL] 创建表失败 {table_name}: {e}")
            return False

    async def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = %s"
        result = await self.fetch_one(sql, (self.config.mysql_database, table_name))
        return result and result[0] > 0

    async def get_table_list(self) -> List[str]:
        """获取所有表名列表"""
        sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name"
        results = await self.fetch_all(sql, (self.config.mysql_database,))
        return [row[0] for row in results]

    async def export_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """导出表数据"""
        sql = f"SELECT * FROM {table_name}"
        async with self.get_connection_context() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(sql)
                rows = await cursor.fetchall()
                return rows

    async def import_table_data(self, table_name: str, data: List[Dict[str, Any]], replace: bool = False) -> int:
        """
        导入表数据

        Args:
            table_name: 表名
            data: 数据列表
            replace: 是否使用 REPLACE INTO（解决主键冲突）
        """
        if not data:
            return 0

        # 获取列名
        columns = list(data[0].keys())

        # 转换时间戳格式（从 Unix 时间戳转为 DATETIME）
        datetime_columns = {'created_at', 'updated_at', 'timestamp', 'review_time'}

        converted_data = []
        for row in data:
            new_row = {}
            for col, val in row.items():
                # 检查是否是需要转换的时间戳列
                if col in datetime_columns and isinstance(val, (int, float)) and val > 1000000000:
                    # Unix 时间戳 -> DATETIME 字符串
                    from datetime import datetime
                    new_row[col] = datetime.fromtimestamp(val).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    new_row[col] = val
            converted_data.append(new_row)

        placeholders = ','.join(['%s' for _ in columns])

        # 使用 REPLACE INTO 或 INSERT INTO
        insert_type = "REPLACE" if replace else "INSERT"
        sql = f"{insert_type} INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

        # 准备参数
        params_list = [tuple(row[col] for col in columns) for row in converted_data]

        return await self.execute_many(sql, params_list)

    @asynccontextmanager
    async def get_connection_context(self):
        """获取连接上下文管理器"""
        # 如果在事务中，使用事务连接
        if self._current_transaction_conn:
            yield self._current_transaction_conn
        else:
            # 否则从池中获取连接
            conn = await self.connection_pool.get_connection()
            try:
                yield conn
            finally:
                await self.connection_pool.return_connection(conn)

    @property
    def db_type(self) -> DatabaseType:
        """获取数据库类型"""
        return DatabaseType.MYSQL

    def convert_ddl(self, sqlite_ddl: str) -> str:
        """
        转换SQLite DDL到MySQL DDL

        主要转换:
        1. INTEGER PRIMARY KEY AUTOINCREMENT -> INT PRIMARY KEY AUTO_INCREMENT
        2. INTEGER -> INT
        3. REAL -> DOUBLE
        4. BOOLEAN -> TINYINT(1)
        5. TEXT -> TEXT/VARCHAR
        6. TIMESTAMP DEFAULT CURRENT_TIMESTAMP -> TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        7. DATETIME DEFAULT CURRENT_TIMESTAMP -> DATETIME DEFAULT CURRENT_TIMESTAMP
        """
        mysql_ddl = sqlite_ddl

        # 替换数据类型
        mysql_ddl = re.sub(
            r'\bINTEGER PRIMARY KEY AUTOINCREMENT\b',
            'INT PRIMARY KEY AUTO_INCREMENT',
            mysql_ddl,
            flags=re.IGNORECASE
        )
        mysql_ddl = re.sub(r'\bINTEGER\b', 'INT', mysql_ddl, flags=re.IGNORECASE)
        mysql_ddl = re.sub(r'\bREAL\b', 'DOUBLE', mysql_ddl, flags=re.IGNORECASE)
        mysql_ddl = re.sub(r'\bBOOLEAN\b', 'TINYINT(1)', mysql_ddl, flags=re.IGNORECASE)

        # 移除SQLite特有的PRAGMA
        mysql_ddl = re.sub(r'PRAGMA\s+\w+\s*=\s*\w+;?', '', mysql_ddl, flags=re.IGNORECASE)

        # 替换IF NOT EXISTS (MySQL支持)
        # 无需修改，MySQL也支持

        # 添加ENGINE和CHARSET
        if 'CREATE TABLE' in mysql_ddl.upper() and 'ENGINE=' not in mysql_ddl.upper():
            mysql_ddl = mysql_ddl.rstrip().rstrip(';')
            mysql_ddl += ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'

        return mysql_ddl
