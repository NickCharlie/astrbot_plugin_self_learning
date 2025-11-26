"""
SQLite 数据库后端实现
"""
import os
import asyncio
import aiosqlite
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Callable, TypeVar
from contextlib import asynccontextmanager

from astrbot.api import logger

from .backend_interface import (
    IDatabaseBackend,
    DatabaseType,
    DatabaseConfig,
    ConnectionPool
)

T = TypeVar('T')


async def retry_on_lock(func: Callable[..., T], max_retries: int = 3, initial_delay: float = 0.1) -> T:
    """
    对数据库操作进行重试，处理 database is locked 错误

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间（秒）

    Returns:
        函数执行结果
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except (sqlite3.OperationalError, Exception) as e:
            error_msg = str(e)
            if 'database is locked' not in error_msg.lower():
                # 不是锁定错误，直接抛出
                raise

            last_error = e
            if attempt < max_retries:
                logger.warning(f"[SQLite] 数据库锁定，第 {attempt + 1}/{max_retries} 次重试（延迟 {delay:.2f}s）")
                await asyncio.sleep(delay)
                delay *= 2  # 指数退避
            else:
                logger.error(f"[SQLite] 重试 {max_retries} 次后仍失败: {error_msg}")

    # 所有重试都失败
    raise last_error


class SQLiteConnectionPool(ConnectionPool):
    """SQLite连接池"""

    def __init__(self, db_path: str, max_connections: int = 10, min_connections: int = 2):
        self.db_path = db_path
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.pool: asyncio.Queue = asyncio.Queue(maxsize=max_connections)
        self.active_connections = 0
        self.total_connections = 0
        self._lock = asyncio.Lock()

    async def initialize(self):
        """初始化连接池"""
        async with self._lock:
            # 确保目录存在
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # 创建最小数量的连接
            for _ in range(self.min_connections):
                conn = await self._create_connection()
                await self.pool.put(conn)

    async def _create_connection(self) -> aiosqlite.Connection:
        """创建新的数据库连接"""
        # 设置超时时间为30秒，避免database is locked错误
        conn = await aiosqlite.connect(self.db_path, timeout=30.0)

        # 设置连接参数
        await conn.execute('PRAGMA foreign_keys = ON')
        await conn.execute('PRAGMA journal_mode = WAL')
        await conn.execute('PRAGMA synchronous = NORMAL')
        await conn.execute('PRAGMA cache_size = 10000')
        await conn.execute('PRAGMA temp_store = memory')
        await conn.execute('PRAGMA busy_timeout = 30000')  # 设置忙等待超时为30秒（毫秒）
        await conn.commit()

        self.total_connections += 1
        logger.debug(f"[SQLite] 创建新连接，总连接数: {self.total_connections}")
        return conn

    async def get_connection(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        try:
            # 尝试从池中获取连接（非阻塞）
            conn = self.pool.get_nowait()
            self.active_connections += 1
            return conn
        except asyncio.QueueEmpty:
            # 池中无可用连接
            async with self._lock:
                if self.total_connections < self.max_connections:
                    # 可以创建新连接
                    conn = await self._create_connection()
                    self.active_connections += 1
                    return conn
                else:
                    # 达到最大连接数，等待连接归还
                    logger.debug("[SQLite] 连接池已满，等待连接归还...")
                    conn = await self.pool.get()
                    self.active_connections += 1
                    return conn

    async def return_connection(self, conn: aiosqlite.Connection):
        """归还数据库连接"""
        if conn:
            try:
                # 检查连接是否仍然有效
                await conn.execute('SELECT 1')
                await self.pool.put(conn)
                self.active_connections -= 1
            except Exception as e:
                # 连接已损坏，关闭并减少计数
                logger.warning(f"[SQLite] 连接已损坏，关闭连接: {e}")
                try:
                    await conn.close()
                except:
                    pass
                self.total_connections -= 1
                self.active_connections -= 1

    async def close_all(self):
        """关闭所有连接"""
        logger.info("[SQLite] 开始关闭连接池...")

        # 关闭池中的所有连接
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                await conn.close()
                self.total_connections -= 1
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"[SQLite] 关闭连接时出错: {e}")

        logger.info(f"[SQLite] 连接池已关闭，剩余连接数: {self.total_connections}")


class SQLiteBackend(IDatabaseBackend):
    """SQLite数据库后端实现"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection_pool: Optional[SQLiteConnectionPool] = None
        self._current_transaction_conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> bool:
        """初始化数据库连接"""
        try:
            valid, error = self.config.validate()
            if not valid:
                logger.error(f"[SQLite] 配置验证失败: {error}")
                return False

            self.connection_pool = SQLiteConnectionPool(
                db_path=self.config.sqlite_path,
                max_connections=self.config.max_connections,
                min_connections=self.config.min_connections
            )

            await self.connection_pool.initialize()
            logger.info(f"[SQLite] 数据库初始化成功: {self.config.sqlite_path}")
            return True
        except Exception as e:
            logger.error(f"[SQLite] 初始化失败: {e}", exc_info=True)
            return False

    async def close(self) -> bool:
        """关闭数据库连接"""
        try:
            if self.connection_pool:
                await self.connection_pool.close_all()
            logger.info("[SQLite] 数据库连接已关闭")
            return True
        except Exception as e:
            logger.error(f"[SQLite] 关闭失败: {e}", exc_info=True)
            return False

    async def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """执行SQL语句（带重试机制）"""
        async def _do_execute():
            async with self.get_connection_context() as conn:
                cursor = await conn.execute(sql, params or ())
                await conn.commit()
                return cursor.rowcount
        return await retry_on_lock(_do_execute, max_retries=5)

    async def execute_many(self, sql: str, params_list: List[Tuple]) -> int:
        """批量执行SQL语句（带重试机制）"""
        async def _do_execute_many():
            async with self.get_connection_context() as conn:
                cursor = await conn.executemany(sql, params_list)
                await conn.commit()
                return cursor.rowcount
        return await retry_on_lock(_do_execute_many, max_retries=5)

    async def fetch_one(self, sql: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
        """查询单行数据（带重试机制）"""
        async def _do_fetch_one():
            async with self.get_connection_context() as conn:
                cursor = await conn.execute(sql, params or ())
                return await cursor.fetchone()
        return await retry_on_lock(_do_fetch_one, max_retries=3)

    async def fetch_all(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """查询所有数据（带重试机制）"""
        async def _do_fetch_all():
            async with self.get_connection_context() as conn:
                cursor = await conn.execute(sql, params or ())
                return await cursor.fetchall()
        return await retry_on_lock(_do_fetch_all, max_retries=3)

    async def begin_transaction(self):
        """开始事务"""
        if self._current_transaction_conn is None:
            self._current_transaction_conn = await self.connection_pool.get_connection()
        await self._current_transaction_conn.execute('BEGIN')

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
            await self.execute(schema)
            logger.info(f"[SQLite] 创建表成功: {table_name}")
            return True
        except Exception as e:
            logger.error(f"[SQLite] 创建表失败 {table_name}: {e}")
            return False

    async def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = await self.fetch_one(sql, (table_name,))
        return result is not None

    async def get_table_list(self) -> List[str]:
        """获取所有表名列表"""
        sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        results = await self.fetch_all(sql)
        return [row[0] for row in results]

    async def export_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """导出表数据"""
        sql = f"SELECT * FROM {table_name}"
        async with self.get_connection_context() as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def import_table_data(self, table_name: str, data: List[Dict[str, Any]], replace: bool = False) -> int:
        """
        导入表数据

        Args:
            table_name: 表名
            data: 数据列表
            replace: SQLite 不支持，忽略此参数
        """
        if not data:
            return 0

        # 获取列名
        columns = list(data[0].keys())
        placeholders = ','.join(['?' for _ in columns])

        # SQLite 使用 INSERT OR REPLACE 代替 REPLACE INTO
        insert_type = "INSERT OR REPLACE" if replace else "INSERT"
        sql = f"{insert_type} INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

        # 准备参数
        params_list = [tuple(row[col] for col in columns) for row in data]

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
        return DatabaseType.SQLITE

    def convert_ddl(self, sqlite_ddl: str) -> str:
        """SQLite DDL不需要转换"""
        return sqlite_ddl
