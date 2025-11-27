"""
SQLAlchemy 数据库引擎封装
提供异步数据库引擎和会话工厂
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from astrbot.api import logger
from typing import Optional
import os

from ...models.orm import Base


class DatabaseEngine:
    """
    SQLAlchemy 异步数据库引擎封装

    功能:
    1. 自动识别数据库类型 (SQLite/MySQL)
    2. 创建异步引擎和会话工厂
    3. 支持表结构创建和清理
    4. 连接池管理
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
        self.engine: Optional[create_async_engine] = None
        self.session_factory: Optional[async_sessionmaker] = None

        self._initialize_engine()

    def _initialize_engine(self):
        """初始化数据库引擎"""
        try:
            # 判断数据库类型
            if 'sqlite' in self.database_url.lower():
                self._init_sqlite_engine()
            elif 'mysql' in self.database_url.lower():
                self._init_mysql_engine()
            else:
                raise ValueError(f"不支持的数据库类型: {self.database_url}")

            logger.info(f"✅ [DatabaseEngine] 数据库引擎初始化成功")

        except Exception as e:
            logger.error(f"❌ [DatabaseEngine] 引擎初始化失败: {e}")
            raise

    def _init_sqlite_engine(self):
        """初始化 SQLite 引擎"""
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
            logger.info(f"✅ [DatabaseEngine] 创建数据库目录: {db_dir}")

        # SQLite 配置
        self.engine = create_async_engine(
            db_url,
            echo=self.echo,
            # SQLite 不需要连接池
            poolclass=NullPool,
            # SQLite 特定参数
            connect_args={
                'check_same_thread': False,  # 允许多线程
                'timeout': 30,  # 连接超时
            }
        )

        logger.info(f"✅ [DatabaseEngine] SQLite 引擎创建成功: {db_path}")

    def _init_mysql_engine(self):
        """初始化 MySQL 引擎"""
        # 确保使用 aiomysql 驱动
        if not self.database_url.startswith('mysql+aiomysql'):
            # 尝试转换
            if self.database_url.startswith('mysql://'):
                db_url = self.database_url.replace('mysql://', 'mysql+aiomysql://')
            else:
                db_url = self.database_url
        else:
            db_url = self.database_url

        # MySQL 配置
        self.engine = create_async_engine(
            db_url,
            echo=self.echo,
            # MySQL 连接池配置
            poolclass=QueuePool,
            pool_size=10,  # 连接池大小
            max_overflow=20,  # 最大溢出连接数
            pool_pre_ping=True,  # 连接前 ping，检查连接是否有效
            pool_recycle=3600,  # 1小时回收连接
            # MySQL 特定参数
            connect_args={
                'connect_timeout': 10,  # 连接超时
                'charset': 'utf8mb4',  # 字符集
            }
        )

        logger.info(f"✅ [DatabaseEngine] MySQL 引擎创建成功")

    def _create_session_factory(self):
        """创建会话工厂"""
        if not self.session_factory:
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,  # 提交后不过期对象
                autoflush=False,  # 手动控制 flush
                autocommit=False,  # 手动控制 commit
            )
            logger.debug("[DatabaseEngine] 会话工厂创建成功")

    async def create_tables(self):
        """
        创建所有表

        根据 ORM 模型自动创建表结构
        如果表已存在则跳过
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ [DatabaseEngine] 数据库表结构创建完成")
        except Exception as e:
            logger.error(f"❌ [DatabaseEngine] 创建表失败: {e}")
            raise

    async def drop_tables(self):
        """
        删除所有表

        ⚠️ 危险操作！会删除所有数据
        仅用于测试环境
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.warning("⚠️ [DatabaseEngine] 所有表已删除")
        except Exception as e:
            logger.error(f"❌ [DatabaseEngine] 删除表失败: {e}")
            raise

    def get_session(self) -> AsyncSession:
        """
        获取数据库会话

        Returns:
            AsyncSession: 异步数据库会话

        用法:
            async with engine.get_session() as session:
                # 执行数据库操作
                result = await session.execute(...)
                await session.commit()
        """
        if not self.session_factory:
            self._create_session_factory()
        return self.session_factory()

    async def close(self):
        """
        关闭数据库引擎

        释放所有连接池资源
        """
        if self.engine:
            await self.engine.dispose()
            logger.info("✅ [DatabaseEngine] 数据库引擎已关闭")

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 数据库连接是否正常
        """
        try:
            from sqlalchemy import text

            async with self.get_session() as session:
                # 执行简单查询
                result = await session.execute(text("SELECT 1"))
                result.fetchone()
            return True
        except Exception as e:
            logger.error(f"❌ [DatabaseEngine] 健康检查失败: {e}")
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
        }

    @staticmethod
    def _mask_password(url: str) -> str:
        """隐藏数据库 URL 中的密码"""
        if '@' in url:
            # mysql+aiomysql://user:password@host:port/db
            parts = url.split('@')
            if ':' in parts[0]:
                prefix = parts[0].rsplit(':', 1)[0]
                return f"{prefix}:****@{parts[1]}"
        return url


# ============================================================
# 便捷函数
# ============================================================

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
