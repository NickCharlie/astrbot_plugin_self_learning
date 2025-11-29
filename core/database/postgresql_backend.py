"""
PostgreSQL 数据库后端实现
"""
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Callable, TypeVar
from contextlib import asynccontextmanager

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None

from astrbot.api import logger

from .backend_interface import (
    IDatabaseBackend,
    DatabaseType,
    DatabaseConfig,
    ConnectionPool
)

T = TypeVar('T')


async def retry_on_postgres_error(func: Callable[..., T], max_retries: int = 3, initial_delay: float = 0.1) -> T:
    """
    对 PostgreSQL 数据库操作进行重试，处理临时性错误

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间（秒）

    Returns:
        函数执行结果
    """
    delay = initial_delay
    last_error = None

    # PostgreSQL 可重试的错误码
    RETRYABLE_SQLSTATES = {
        '40001',  # serialization_failure
        '40P01',  # deadlock_detected
        '08003',  # connection_does_not_exist
        '08006',  # connection_failure
        '08000',  # connection_exception
        '57P03',  # cannot_connect_now
    }

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            error_msg = str(e)

            # 检查是否是可重试的错误
            is_retryable = False

            # asyncpg 的异常有 sqlstate 属性
            if hasattr(e, 'sqlstate') and e.sqlstate in RETRYABLE_SQLSTATES:
                is_retryable = True

            # 也检查错误消息
            if any(keyword in error_msg.lower() for keyword in ['deadlock', 'serialization', 'connection', 'timeout']):
                is_retryable = True

            if not is_retryable:
                # 不是可重试的错误，直接抛出
                raise

            last_error = e
            if attempt < max_retries:
                logger.warning(f"[PostgreSQL] 遇到临时错误，第 {attempt + 1}/{max_retries} 次重试（延迟 {delay:.2f}s）: {error_msg}")
                await asyncio.sleep(delay)
                delay *= 2  # 指数退避
            else:
                logger.error(f"[PostgreSQL] 重试 {max_retries} 次后仍失败: {error_msg}")

    # 所有重试都失败
    raise last_error


class PostgreSQLConnectionPool(ConnectionPool):
    """PostgreSQL连接池"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """初始化连接池"""
        if not ASYNCPG_AVAILABLE:
            raise ImportError("asyncpg is not installed. Please install it: pip install asyncpg")

        # 构建连接字符串或使用参数字典
        self.pool = await asyncpg.create_pool(
            host=self.config.postgresql_host,
            port=self.config.postgresql_port,
            user=self.config.postgresql_user,
            password=self.config.postgresql_password,
            database=self.config.postgresql_database,
            min_size=self.config.min_connections,
            max_size=self.config.max_connections,
            command_timeout=self.config.connection_timeout,
            # PostgreSQL 特定设置
            server_settings={
                'search_path': self.config.postgresql_schema,
            }
        )
        logger.info(f"[PostgreSQL] 连接池初始化成功: {self.config.postgresql_host}:{self.config.postgresql_port}/{self.config.postgresql_database}")

    async def get_connection(self):
        """获取数据库连接"""
        return await self.pool.acquire()

    async def return_connection(self, conn):
        """归还数据库连接"""
        if conn:
            await self.pool.release(conn)

    async def close_all(self):
        """关闭所有连接"""
        if self.pool:
            await self.pool.close()
            logger.info("[PostgreSQL] 连接池已关闭")


class PostgreSQLBackend(IDatabaseBackend):
    """PostgreSQL数据库后端实现"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection_pool: Optional[PostgreSQLConnectionPool] = None
        self._current_transaction_conn: Optional[asyncpg.Connection] = None

    async def initialize(self) -> bool:
        """初始化数据库连接"""
        try:
            if not ASYNCPG_AVAILABLE:
                logger.error("[PostgreSQL] asyncpg未安装，请运行: pip install asyncpg")
                return False

            valid, error = self.config.validate()
            if not valid:
                logger.error(f"[PostgreSQL] 配置验证失败: {error}")
                return False

            self.connection_pool = PostgreSQLConnectionPool(self.config)
            await self.connection_pool.initialize()
            logger.info("[PostgreSQL] 数据库初始化成功")
            return True
        except Exception as e:
            logger.error(f"[PostgreSQL] 初始化失败: {e}", exc_info=True)
            return False

    async def close(self) -> bool:
        """关闭数据库连接"""
        try:
            if self.connection_pool:
                await self.connection_pool.close_all()
            logger.info("[PostgreSQL] 数据库连接已关闭")
            return True
        except Exception as e:
            logger.error(f"[PostgreSQL] 关闭失败: {e}", exc_info=True)
            return False

    async def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """执行SQL语句（带重试机制）"""
        async def _do_execute():
            async with self.get_connection_context() as conn:
                # PostgreSQL 使用 $1, $2 而不是 ?
                converted_sql = self._convert_placeholders(sql)
                result = await conn.execute(converted_sql, *(params or ()))
                # asyncpg 的 execute 返回状态字符串，如 "INSERT 0 1"
                # 我们需要解析出影响的行数
                return self._parse_row_count(result)
        return await retry_on_postgres_error(_do_execute, max_retries=3)

    async def execute_many(self, sql: str, params_list: List[Tuple]) -> int:
        """批量执行SQL语句（带重试机制）"""
        async def _do_execute_many():
            async with self.get_connection_context() as conn:
                converted_sql = self._convert_placeholders(sql)
                # asyncpg 使用 executemany
                await conn.executemany(converted_sql, params_list)
                # executemany 不返回行数，返回参数列表长度
                return len(params_list)
        return await retry_on_postgres_error(_do_execute_many, max_retries=3)

    async def fetch_one(self, sql: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
        """查询单行数据（带重试机制）"""
        async def _do_fetch_one():
            async with self.get_connection_context() as conn:
                converted_sql = self._convert_placeholders(sql)
                row = await conn.fetchrow(converted_sql, *(params or ()))
                # asyncpg 返回 Record 对象，转为 tuple
                return tuple(row) if row else None
        return await retry_on_postgres_error(_do_fetch_one, max_retries=2)

    async def fetch_all(self, sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
        """查询所有数据（带重试机制）"""
        async def _do_fetch_all():
            async with self.get_connection_context() as conn:
                converted_sql = self._convert_placeholders(sql)
                rows = await conn.fetch(converted_sql, *(params or ()))
                # 转换为 tuple 列表
                return [tuple(row) for row in rows]
        return await retry_on_postgres_error(_do_fetch_all, max_retries=2)

    async def begin_transaction(self):
        """开始事务"""
        if self._current_transaction_conn is None:
            self._current_transaction_conn = await self.connection_pool.get_connection()
        # asyncpg 使用 transaction() 上下文管理器，这里手动开始
        self._transaction = self._current_transaction_conn.transaction()
        await self._transaction.start()

    async def commit(self):
        """提交事务"""
        if self._current_transaction_conn and hasattr(self, '_transaction'):
            await self._transaction.commit()
            await self.connection_pool.return_connection(self._current_transaction_conn)
            self._current_transaction_conn = None
            self._transaction = None

    async def rollback(self):
        """回滚事务"""
        if self._current_transaction_conn and hasattr(self, '_transaction'):
            await self._transaction.rollback()
            await self.connection_pool.return_connection(self._current_transaction_conn)
            self._current_transaction_conn = None
            self._transaction = None

    async def create_table(self, table_name: str, schema: str) -> bool:
        """创建表"""
        try:
            # 转换SQLite DDL到PostgreSQL DDL
            postgres_schema = self.convert_ddl(schema)
            await self.execute(postgres_schema)
            logger.info(f"[PostgreSQL] 创建表成功: {table_name}")
            return True
        except Exception as e:
            logger.error(f"[PostgreSQL] 创建表失败 {table_name}: {e}")
            return False

    async def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = $1 AND table_name = $2
        """
        result = await self.fetch_one(sql, (self.config.postgresql_schema, table_name))
        return result and result[0] > 0

    async def get_table_list(self) -> List[str]:
        """获取所有表名列表"""
        sql = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            ORDER BY table_name
        """
        results = await self.fetch_all(sql, (self.config.postgresql_schema,))
        return [row[0] for row in results]

    async def export_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """导出表数据"""
        sql = f"SELECT * FROM {table_name}"
        async with self.get_connection_context() as conn:
            converted_sql = self._convert_placeholders(sql)
            rows = await conn.fetch(converted_sql)
            # asyncpg Record 可以直接转为 dict
            return [dict(row) for row in rows]

    async def import_table_data(self, table_name: str, data: List[Dict[str, Any]], replace: bool = False) -> int:
        """
        导入表数据

        Args:
            table_name: 表名
            data: 数据列表
            replace: 是否使用 UPSERT（ON CONFLICT）
        """
        if not data:
            return 0

        # 获取列名
        columns = list(data[0].keys())

        # 转换时间戳格式（从 Unix 时间戳转为 TIMESTAMP）
        datetime_columns = {'created_at', 'updated_at', 'timestamp', 'review_time'}

        converted_data = []
        for row in data:
            new_row = {}
            for col, val in row.items():
                # 检查是否是需要转换的时间戳列
                if col in datetime_columns and isinstance(val, (int, float)) and val > 1000000000:
                    # Unix 时间戳 -> TIMESTAMP
                    from datetime import datetime
                    new_row[col] = datetime.fromtimestamp(val)
                else:
                    new_row[col] = val
            converted_data.append(new_row)

        # PostgreSQL 使用 $1, $2, ... 占位符
        placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])

        if replace:
            # PostgreSQL 使用 ON CONFLICT 实现 UPSERT
            # 需要知道主键列名，这里假设第一个列是主键
            primary_key = columns[0]
            update_cols = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns[1:]])
            sql = f"""
                INSERT INTO {table_name} ({','.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT ({primary_key})
                DO UPDATE SET {update_cols}
            """
        else:
            sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"

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
        return DatabaseType.POSTGRESQL

    def _convert_placeholders(self, sql: str) -> str:
        """
        将 ? 占位符转换为 PostgreSQL 的 $1, $2, ... 格式

        注意：这个简单实现不处理字符串中的 ?，实际使用中可能需要更复杂的解析
        """
        # 简单替换：按顺序替换所有 ?
        counter = 1
        result = []
        in_string = False
        escape_next = False

        for char in sql:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            if char in ("'", '"'):
                in_string = not in_string
                result.append(char)
                continue

            if char == '?' and not in_string:
                result.append(f'${counter}')
                counter += 1
            else:
                result.append(char)

        return ''.join(result)

    def _parse_row_count(self, status: str) -> int:
        """
        解析 PostgreSQL 返回的状态字符串，提取受影响的行数

        例如: "INSERT 0 1" -> 1, "UPDATE 3" -> 3, "DELETE 5" -> 5
        """
        try:
            parts = status.split()
            if len(parts) >= 2:
                # 最后一个数字通常是行数
                return int(parts[-1])
            return 0
        except (ValueError, IndexError):
            return 0

    def convert_ddl(self, sqlite_ddl: str) -> str:
        """
        转换SQLite DDL到PostgreSQL DDL

        主要转换:
        1. INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
        2. INTEGER -> INTEGER (PostgreSQL 也支持)
        3. REAL -> DOUBLE PRECISION
        4. BOOLEAN -> BOOLEAN (PostgreSQL 原生支持)
        5. TEXT -> TEXT (PostgreSQL 支持)
        6. DATETIME -> TIMESTAMP
        7. 移除 IF NOT EXISTS（PostgreSQL 9.1+ 支持，保留）
        """
        postgres_ddl = sqlite_ddl

        # 替换 AUTOINCREMENT 为 SERIAL
        postgres_ddl = re.sub(
            r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b',
            'SERIAL PRIMARY KEY',
            postgres_ddl,
            flags=re.IGNORECASE
        )

        # 替换 REAL 为 DOUBLE PRECISION
        postgres_ddl = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', postgres_ddl, flags=re.IGNORECASE)

        # 替换 DATETIME 为 TIMESTAMP
        postgres_ddl = re.sub(r'\bDATETIME\b', 'TIMESTAMP', postgres_ddl, flags=re.IGNORECASE)

        # 移除SQLite特有的PRAGMA
        postgres_ddl = re.sub(r'PRAGMA\s+\w+\s*=\s*\w+;?', '', postgres_ddl, flags=re.IGNORECASE)

        # 替换 strftime('%s', 'now') 为 extract(epoch from now())
        postgres_ddl = re.sub(
            r"strftime\s*\(\s*'%s'\s*,\s*'now'\s*\)",
            "extract(epoch from now())",
            postgres_ddl,
            flags=re.IGNORECASE
        )

        # 替换 CURRENT_TIMESTAMP
        # PostgreSQL 支持 CURRENT_TIMESTAMP，无需修改

        return postgres_ddl
