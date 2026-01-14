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

        # 配置 SQLite 为 WAL 模式以支持并发读写，避免数据库锁定
        from sqlalchemy import event
        from sqlalchemy.pool import Pool

        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            """在每个连接建立时设置 SQLite PRAGMA"""
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=memory")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        logger.info(f"✅ [DatabaseEngine] SQLite 引擎创建成功 (WAL模式): {db_path}")

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
        # 使用 NullPool 避免跨线程/跨事件循环问题
        # NullPool 不缓存连接，每次请求都创建新连接，适合多线程环境
        self.engine = create_async_engine(
            db_url,
            echo=self.echo,
            # 使用 NullPool 避免连接池在不同事件循环间共享的问题
            poolclass=NullPool,
            # MySQL 特定参数
            connect_args={
                'connect_timeout': 10,  # 连接超时
                'charset': 'utf8mb4',  # 字符集
            }
        )

        logger.info(f"✅ [DatabaseEngine] MySQL 引擎创建成功 (使用 NullPool 支持多线程)")


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

            # 执行数据库迁移
            await self.migrate_schema()

        except Exception as e:
            # 检查是否是索引已存在的错误（这是正常情况，可以忽略）
            error_msg = str(e).lower()
            if 'index' in error_msg and 'already exists' in error_msg:
                logger.info("✅ [DatabaseEngine] 数据库表和索引已存在，跳过创建")
                # 即使索引已存在，仍然执行迁移以添加新字段
                await self.migrate_schema()
            else:
                logger.error(f"❌ [DatabaseEngine] 创建表失败: {e}")
                raise

    async def migrate_schema(self):
        """
        数据库结构迁移

        为已存在的表添加新字段
        """
        try:
            from sqlalchemy import text

            async with self.get_session() as session:
                # 检查数据库类型
                is_mysql = 'mysql' in self.database_url.lower()

                if is_mysql:
                    # MySQL 迁移
                    await self._migrate_mysql(session)
                else:
                    # SQLite 迁移
                    await self._migrate_sqlite(session)

        except Exception as e:
            logger.warning(f"⚠️ [DatabaseEngine] 数据库迁移出现异常（可能字段已存在）: {e}")

    async def _migrate_mysql(self, session):
        """MySQL 数据库迁移"""
        from sqlalchemy import text

        # 1. 修复 filtered_messages 的 quality_score 字段问题
        # 旧版本可能创建了 quality_score DOUBLE，但应该是 quality_scores TEXT
        try:
            check_sql = text("""
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'filtered_messages'
                AND COLUMN_NAME IN ('quality_score', 'quality_scores')
            """)
            result = await session.execute(check_sql)
            existing_columns = {row[0]: row[1] for row in result.fetchall()}

            # 如果存在错误的 quality_score 字段，删除它
            if 'quality_score' in existing_columns:
                logger.info("[Migration] 检测到旧字段 quality_score，准备删除...")
                await session.execute(text("ALTER TABLE filtered_messages DROP COLUMN quality_score"))
                await session.commit()
                logger.info("✅ [Migration] 已删除 filtered_messages.quality_score 旧字段")

            # 如果 quality_scores 不存在，添加它
            if 'quality_scores' not in existing_columns:
                await session.execute(text("ALTER TABLE filtered_messages ADD COLUMN quality_scores TEXT"))
                await session.commit()
                logger.info("✅ [Migration] 已为 filtered_messages 表添加 quality_scores 字段")

        except Exception as e:
            logger.warning(f"⚠️ [Migration] quality_scores 字段迁移失败: {e}")
            await session.rollback()

        # 2. 添加其他缺失字段
        migrations = [
            # raw_messages 表
            ("raw_messages", "message_id", "ALTER TABLE raw_messages ADD COLUMN message_id VARCHAR(255)"),
            ("raw_messages", "reply_to", "ALTER TABLE raw_messages ADD COLUMN reply_to VARCHAR(255)"),

            # filtered_messages 表
            ("filtered_messages", "processed", "ALTER TABLE filtered_messages ADD COLUMN processed TINYINT(1) DEFAULT 0"),
            ("filtered_messages", "filter_reason", "ALTER TABLE filtered_messages ADD COLUMN filter_reason TEXT"),

            # psychological_state_components 表 - 添加外键字段（允许 NULL 以兼容传统数据）
            ("psychological_state_components", "composite_state_id", "ALTER TABLE psychological_state_components ADD COLUMN composite_state_id INT NULL"),
        ]

        for table, column, sql in migrations:
            try:
                # 检查字段是否存在
                check_sql = text(f"""
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{table}'
                    AND COLUMN_NAME = '{column}'
                """)
                result = await session.execute(check_sql)
                count = result.scalar()

                if count == 0:
                    # 字段不存在，添加字段
                    await session.execute(text(sql))
                    await session.commit()
                    logger.info(f"✅ [Migration] 已为 {table} 表添加 {column} 字段")

            except Exception as e:
                logger.debug(f"[Migration] {table}.{column} 迁移跳过: {e}")
                await session.rollback()

        # 3. 修复时间戳字段类型（DATETIME -> BIGINT）
        # 安全迁移策略:添加临时字段->转换数据->替换字段
        timestamp_fields = [
            ("raw_messages", "timestamp"),
            ("raw_messages", "created_at"),
            ("filtered_messages", "timestamp"),
            ("filtered_messages", "created_at"),
            ("bot_messages", "timestamp"),
            ("bot_messages", "created_at"),
            ("learning_performance_history", "timestamp"),
            ("learning_performance_history", "created_at"),
            ("jargon", "created_at"),  # ✨ 新增：黑话表
            ("jargon", "updated_at"),  # ✨ 新增：黑话表
            ("social_relations", "created_at"),  # ✨ 新增：社交关系表
            ("social_relations", "updated_at"),  # ✨ 新增：社交关系表
        ]

        for table, column in timestamp_fields:
            try:
                # 检查字段类型
                check_sql = text(f"""
                    SELECT DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{table}'
                    AND COLUMN_NAME = '{column}'
                """)
                result = await session.execute(check_sql)
                data_type = result.scalar()

                # 如果是 DATETIME 或 TIMESTAMP 类型,需要安全转换为 BIGINT
                if data_type and data_type.upper() in ('DATETIME', 'TIMESTAMP'):
                    logger.warning(f"⚠️ [Migration] 发现 {table}.{column} 为 {data_type} 类型,开始安全转换为 BIGINT...")

                    temp_column = f"{column}_bigint_temp"

                    # 步骤1: 添加临时 BIGINT 列
                    await session.execute(text(f"ALTER TABLE {table} ADD COLUMN {temp_column} BIGINT"))
                    await session.commit()
                    logger.debug(f"[Migration] 已添加临时列 {table}.{temp_column}")

                    # 步骤2: 将 DATETIME 转换为 Unix 时间戳并复制到临时列
                    await session.execute(text(f"""
                        UPDATE {table}
                        SET {temp_column} = UNIX_TIMESTAMP({column})
                        WHERE {column} IS NOT NULL
                    """))
                    await session.commit()
                    logger.debug(f"[Migration] 已将 {table}.{column} 数据转换为 Unix 时间戳")

                    # 步骤3: 删除原列
                    await session.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                    await session.commit()
                    logger.debug(f"[Migration] 已删除原列 {table}.{column}")

                    # 步骤4: 重命名临时列为原列名
                    await session.execute(text(f"ALTER TABLE {table} CHANGE COLUMN {temp_column} {column} BIGINT NOT NULL"))
                    await session.commit()

                    logger.info(f"✅ [Migration] 已安全转换 {table}.{column} 从 {data_type} 到 BIGINT")

            except Exception as e:
                logger.warning(f"⚠️ [Migration] {table}.{column} 类型转换失败: {e}")
                await session.rollback()

    async def _migrate_sqlite(self, session):
        """SQLite 数据库迁移"""
        from sqlalchemy import text

        # 0. 首先检查表是否存在
        try:
            check_table_sql = text("SELECT name FROM sqlite_master WHERE type='table' AND name='filtered_messages'")
            result = await session.execute(check_table_sql)
            table_exists = result.fetchone() is not None

            if not table_exists:
                logger.debug("[Migration] filtered_messages 表不存在，跳过迁移")
                return
        except Exception as e:
            logger.debug(f"[Migration] 检查表存在性失败: {e}")
            return

        # 1. 修复 filtered_messages 的 quality_score 字段问题
        # 旧版本可能创建了 quality_score REAL，但应该是 quality_scores TEXT
        try:
            check_sql = text("PRAGMA table_info(filtered_messages)")
            result = await session.execute(check_sql)
            columns_info = {row[1]: row[2] for row in result.fetchall()}  # {column_name: column_type}

            # 如果存在错误的 quality_score 字段，需要删除
            # 注意：SQLite 不支持直接 DROP COLUMN，需要重建表
            if 'quality_score' in columns_info and 'quality_scores' not in columns_info:
                logger.info("[Migration] 检测到旧字段 quality_score，准备迁移为 quality_scores...")

                # SQLite 不支持直接修改列，但我们可以添加新列
                await session.execute(text("ALTER TABLE filtered_messages ADD COLUMN quality_scores TEXT"))
                await session.commit()
                logger.info("✅ [Migration] 已为 filtered_messages 添加 quality_scores 字段 (保留旧的 quality_score 字段)")

            elif 'quality_scores' not in columns_info:
                # 两个字段都不存在，直接添加正确的字段
                await session.execute(text("ALTER TABLE filtered_messages ADD COLUMN quality_scores TEXT"))
                await session.commit()
                logger.info("✅ [Migration] 已为 filtered_messages 表添加 quality_scores 字段")

        except Exception as e:
            logger.debug(f"⚠️ [Migration] quality_scores 字段迁移跳过: {e}")
            await session.rollback()

        # 2. 添加其他缺失字段
        migrations = [
            # raw_messages 表
            ("raw_messages", "message_id", "ALTER TABLE raw_messages ADD COLUMN message_id TEXT"),
            ("raw_messages", "reply_to", "ALTER TABLE raw_messages ADD COLUMN reply_to TEXT"),

            # filtered_messages 表
            ("filtered_messages", "processed", "ALTER TABLE filtered_messages ADD COLUMN processed BOOLEAN DEFAULT 0"),
            ("filtered_messages", "filter_reason", "ALTER TABLE filtered_messages ADD COLUMN filter_reason TEXT"),

            # psychological_state_components 表 - 添加外键字段（允许 NULL 以兼容传统数据）
            ("psychological_state_components", "composite_state_id", "ALTER TABLE psychological_state_components ADD COLUMN composite_state_id INTEGER NULL"),
        ]

        for table, column, sql in migrations:
            try:
                # 使用 PRAGMA 检查字段是否存在
                check_sql = text(f"PRAGMA table_info({table})")
                result = await session.execute(check_sql)
                columns = [row[1] for row in result.fetchall()]

                if column not in columns:
                    # 字段不存在，添加字段
                    await session.execute(text(sql))
                    await session.commit()
                    logger.info(f"✅ [Migration] 已为 {table} 表添加 {column} 字段")

            except Exception as e:
                logger.debug(f"[Migration] {table}.{column} 迁移跳过: {e}")
                await session.rollback()

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
