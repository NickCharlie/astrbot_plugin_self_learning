"""
SQLAlchemy 数据库引擎封装
提供异步数据库引擎和会话工厂

支持跨线程/跨事件循环使用：
当 WebUI 等组件在独立线程中运行自己的 event loop 时，
引擎会自动为每个 event loop 创建独立的 async engine，
避免 "Task got Future attached to a different loop" 错误。
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool
from sqlalchemy import types as sa_types
from astrbot.api import logger
from typing import Optional
import asyncio
import threading
import os

from ...models.orm import Base


class DatabaseEngine:
    """
    SQLAlchemy 异步数据库引擎封装

    功能:
    1. 自动识别数据库类型 (SQLite/MySQL)
    2. 创建异步引擎和会话工厂
    3. 支持表结构创建和清理
    4. 跨线程/跨事件循环安全（per-loop engine）
    """

    def __init__(self, database_url: str, echo: bool = False):
        """
        初始化数据库引擎

        Args:
            database_url: 数据库连接 URL
                - SQLite: "sqlite:///path/to/db.db"
                - MySQL: "mysql+aiomysql://user:pass@host:port/dbname"
            echo: 是否打印 SQL 语句（调试用）
        """
        self.database_url = database_url
        self.echo = echo

        # 主引擎（在构造时创建，用于 create_tables / health_check 等管理操作）
        self.engine = None
        self.session_factory: Optional[async_sessionmaker] = None

        # 跨线程支持：per-loop 引擎和会话工厂
        self._loop_engines: dict[int, object] = {}
        self._loop_session_factories: dict[int, async_sessionmaker] = {}
        self._lock = threading.Lock()
        self._main_loop_id: Optional[int] = None

        self._initialize_engine()

    def _initialize_engine(self):
        """初始化主数据库引擎"""
        try:
            self.engine = self._create_engine()
            logger.info("[DatabaseEngine] 数据库引擎初始化成功")
        except Exception as e:
            logger.error(f"[DatabaseEngine] 引擎初始化失败: {e}")
            raise

    def _create_engine(self):
        """根据数据库类型创建一个新的 async engine"""
        if 'sqlite' in self.database_url.lower():
            return self._create_sqlite_engine()
        elif 'mysql' in self.database_url.lower():
            return self._create_mysql_engine()
        else:
            raise ValueError(f"不支持的数据库类型: {self.database_url}")

    def _create_sqlite_engine(self):
        """创建 SQLite 引擎实例"""
        # 转换为 aiosqlite 驱动
        if not self.database_url.startswith('sqlite+aiosqlite'):
            db_path = self.database_url.replace('sqlite:///', '')
            db_url = f"sqlite+aiosqlite:///{db_path}"
        else:
            db_url = self.database_url

        # 确保数据库目录存在
        db_path = db_url.replace('sqlite+aiosqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"[DatabaseEngine] 创建数据库目录: {db_dir}")

        # SQLite 配置
        # StaticPool reuses a single connection, avoiding per-query overhead
        engine = create_async_engine(
            db_url,
            echo=self.echo,
            poolclass=StaticPool,
            connect_args={
                'check_same_thread': False,
                'timeout': 30,
            }
        )

        # 配置 SQLite 为 WAL 模式以支持并发读写
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=memory")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA mmap_size=268435456")
            cursor.close()

        logger.debug(f"[DatabaseEngine] SQLite 引擎创建成功 (WAL模式): {db_path}")
        return engine

    def _create_mysql_engine(self):
        """创建 MySQL 引擎实例"""
        if not self.database_url.startswith('mysql+aiomysql'):
            if self.database_url.startswith('mysql://'):
                db_url = self.database_url.replace('mysql://', 'mysql+aiomysql://')
            else:
                db_url = self.database_url
        else:
            db_url = self.database_url

        engine = create_async_engine(
            db_url,
            echo=self.echo,
            poolclass=NullPool,
            connect_args={
                'connect_timeout': 10,
                'charset': 'utf8mb4',
            }
        )

        logger.debug("[DatabaseEngine] MySQL 引擎创建成功 (NullPool)")
        return engine

    def _get_engine_for_current_loop(self):
        """
        获取当前 event loop 对应的引擎。

        - 主线程（首次调用时记录）：使用 self.engine
        - 其他线程的 event loop：自动创建独立引擎
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的 loop，返回主引擎
            return self.engine

        loop_id = id(loop)

        # 首次调用时记录主 loop
        if self._main_loop_id is None:
            self._main_loop_id = loop_id
            return self.engine

        # 主 loop 直接返回
        if loop_id == self._main_loop_id:
            return self.engine

        # 其他 loop：获取或创建独立引擎
        if loop_id not in self._loop_engines:
            with self._lock:
                if loop_id not in self._loop_engines:
                    engine = self._create_engine()
                    self._loop_engines[loop_id] = engine
                    logger.info(f"[DatabaseEngine] 为 event loop {loop_id} 创建了独立引擎（跨线程访问）")
        return self._loop_engines[loop_id]

    def _get_session_factory_for_engine(self, engine) -> async_sessionmaker:
        """获取指定引擎对应的会话工厂"""
        engine_id = id(engine)

        # 主引擎用 self.session_factory
        if engine is self.engine:
            if not self.session_factory:
                self.session_factory = async_sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autoflush=False,
                    autocommit=False,
                )
                logger.debug("[DatabaseEngine] 主会话工厂创建成功")
            return self.session_factory

        # 其他引擎用 per-loop 工厂
        if engine_id not in self._loop_session_factories:
            with self._lock:
                if engine_id not in self._loop_session_factories:
                    self._loop_session_factories[engine_id] = async_sessionmaker(
                        engine,
                        class_=AsyncSession,
                        expire_on_commit=False,
                        autoflush=False,
                        autocommit=False,
                    )
                    logger.debug(f"[DatabaseEngine] 为引擎 {engine_id} 创建会话工厂")
        return self._loop_session_factories[engine_id]

    def _create_session_factory(self):
        """创建主会话工厂（保持向后兼容）"""
        if not self.session_factory:
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
            logger.debug("[DatabaseEngine] 会话工厂创建成功")

    async def create_tables(self, enable_auto_migration: bool = False):
        """
        创建所有表并补齐缺失列

        始终执行 create_all(checkfirst=True) 确保所有 ORM 表存在。
        enable_auto_migration 控制是否额外执行列级自动迁移。

        Args:
            enable_auto_migration: 是否启用列级自动迁移（默认禁用）
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("[DatabaseEngine] 数据库表结构同步完成")

            if enable_auto_migration:
                await self._auto_add_missing_columns()

        except Exception as e:
            error_msg = str(e).lower()
            if 'index' in error_msg and 'already exists' in error_msg:
                logger.info("[DatabaseEngine] 数据库表和索引已存在，跳过创建")
            else:
                logger.error(f"[DatabaseEngine] 创建表失败: {e}")
                raise

    async def _auto_add_missing_columns(self):
        """检测并补齐已有表的缺失列（轻量级 auto-migration）"""
        try:
            from sqlalchemy import text, inspect as sa_inspect

            async with self.engine.begin() as conn:
                # 获取数据库中实际的列信息
                def _get_existing_columns(sync_conn):
                    insp = sa_inspect(sync_conn)
                    result = {}
                    for table_name in insp.get_table_names():
                        result[table_name] = {
                            col['name'] for col in insp.get_columns(table_name)
                        }
                    return result

                existing = await conn.run_sync(_get_existing_columns)

                # 创建 ORM 中定义但数据库中不存在的新表
                missing_tables = [
                    t for t in Base.metadata.sorted_tables
                    if t.name not in existing
                ]
                if missing_tables:
                    await conn.run_sync(
                        Base.metadata.create_all,
                        tables=missing_tables,
                        checkfirst=False,
                    )
                    names = [t.name for t in missing_tables]
                    logger.info(
                        f"[DatabaseEngine] 自动创建缺失表: {', '.join(names)}"
                    )

                # 对比 ORM 定义，收集需要 ALTER 的列
                alter_statements = []
                for table in Base.metadata.sorted_tables:
                    if table.name not in existing:
                        continue  # 刚创建的新表，无需 ALTER
                    db_cols = existing[table.name]
                    for col in table.columns:
                        if col.name not in db_cols:
                            col_type = col.type.compile(self.engine.dialect)
                            nullable = "NULL" if col.nullable else "NOT NULL"
                            default = ""
                            # MySQL/MariaDB 不允许 TEXT/BLOB 列有 DEFAULT 值
                            is_mysql = self.engine.dialect.name in ("mysql", "mariadb")
                            is_text_type = isinstance(
                                col.type,
                                (sa_types.Text, sa_types.LargeBinary, sa_types.JSON),
                            )
                            skip_default = is_mysql and is_text_type
                            if not skip_default:
                                if col.server_default is not None:
                                    default = f" DEFAULT {col.server_default.arg!r}"
                                elif col.default is not None and col.default.is_scalar:
                                    default = f" DEFAULT {col.default.arg!r}"
                            alter_statements.append(
                                f"ALTER TABLE `{table.name}` ADD COLUMN "
                                f"`{col.name}` {col_type} {nullable}{default}"
                            )

                if alter_statements:
                    for stmt in alter_statements:
                        try:
                            await conn.execute(text(stmt))
                            logger.info(f"[DatabaseEngine] 自动迁移: {stmt}")
                        except Exception as col_err:
                            # 列可能已经被其他实例添加
                            if 'duplicate column' in str(col_err).lower():
                                pass
                            else:
                                logger.warning(
                                    f"[DatabaseEngine] 自动迁移列失败: {col_err}"
                                )
                else:
                    logger.debug("[DatabaseEngine] 所有表列已与 ORM 模型一致")

        except Exception as e:
            logger.warning(f"[DatabaseEngine] 自动列迁移检测失败（不影响运行）: {e}")

    async def drop_tables(self):
        """
        删除所有表

        危险操作！会删除所有数据，仅用于测试环境
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.warning("[DatabaseEngine] 所有表已删除")
        except Exception as e:
            logger.error(f"[DatabaseEngine] 删除表失败: {e}")
            raise

    def get_session(self) -> AsyncSession:
        """
        获取数据库会话（自动适配当前 event loop）

        跨线程调用时会自动使用该线程对应的引擎，
        避免 event loop 冲突。

        Returns:
            AsyncSession: 异步数据库会话

        用法:
            async with engine.get_session() as session:
                result = await session.execute(...)
                await session.commit()
        """
        engine = self._get_engine_for_current_loop()
        factory = self._get_session_factory_for_engine(engine)
        return factory()

    async def close(self):
        """
        关闭所有数据库引擎（包括跨线程创建的）

        释放所有连接池资源
        """
        # 关闭主引擎
        if self.engine:
            await self.engine.dispose()

        # 关闭所有 per-loop 引擎
        for loop_id, engine in list(self._loop_engines.items()):
            try:
                await engine.dispose()
            except Exception as e:
                logger.debug(f"[DatabaseEngine] 关闭 loop {loop_id} 引擎时忽略错误: {e}")

        self._loop_engines.clear()
        self._loop_session_factories.clear()
        logger.info("[DatabaseEngine] 所有数据库引擎已关闭")

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 数据库连接是否正常
        """
        try:
            from sqlalchemy import text

            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.fetchone()
            return True
        except Exception as e:
            logger.error(f"[DatabaseEngine] 健康检查失败: {e}")
            return False

    def get_engine_info(self) -> dict:
        """
        获取引擎信息

        Returns:
            dict: 引擎配置信息
        """
        return {
            'database_type': 'SQLite' if 'sqlite' in self.database_url else 'MySQL',
            'database_url': self._mask_password(self.database_url),
            'echo': self.echo,
            'pool_size': getattr(self.engine.pool, 'size', 'N/A'),
            'max_overflow': getattr(self.engine.pool, 'overflow', 'N/A'),
            'active_loops': len(self._loop_engines) + 1,
        }

    @staticmethod
    def _mask_password(url: str) -> str:
        """隐藏数据库 URL 中的密码"""
        if '@' in url:
            parts = url.split('@')
            if ':' in parts[0]:
                prefix = parts[0].rsplit(':', 1)[0]
                return f"{prefix}:****@{parts[1]}"
        return url


# 便捷函数

def create_database_engine(database_url: str, echo: bool = False) -> DatabaseEngine:
    """
    创建数据库引擎（便捷函数）

    Args:
        database_url: 数据库连接 URL
        echo: 是否打印 SQL 语句

    Returns:
        DatabaseEngine: 数据库引擎实例

    Examples:
        # SQLite
        engine = create_database_engine('sqlite:///data/database.db')

        # MySQL
        engine = create_database_engine('mysql+aiomysql://user:pass@localhost/db')
    """
    return DatabaseEngine(database_url, echo)
