"""
数据库管理器 - 管理分群数据库和数据持久化 即将弃用
"""
import os
import json
import aiosqlite
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from astrbot.api import logger

from ...config import PluginConfig
from ...constants import UPDATE_TYPE_EXPRESSION_LEARNING
from ...exceptions import DataStorageError

from ...core.patterns import AsyncServiceBase

# 导入数据库后端
from ...core.database import (
    DatabaseFactory,
    DatabaseConfig,
    DatabaseType,
    IDatabaseBackend
)

# 导入ORM支持
from ...core.database.engine import DatabaseEngine
from ...repositories.reinforcement_repository import (
    ReinforcementLearningRepository,
    PersonaFusionRepository,
    StrategyOptimizationRepository
)
from ...repositories.learning_repository import (
    LearningBatchRepository,
    LearningSessionRepository,
    StyleLearningReviewRepository,
    PersonaLearningReviewRepository
)
from ...repositories.message_repository import (
    ConversationContextRepository,
    ConversationTopicClusteringRepository,
    ConversationQualityMetricsRepository,
    ContextSimilarityCacheRepository
)
from ...repositories.jargon_repository import (
    JargonRepository
)


class DatabaseManager(AsyncServiceBase):
    """数据库管理器 - 使用连接池管理数据库连接，支持SQLite和MySQL"""

    def __init__(self, config: PluginConfig, context=None, skip_table_init: bool = False):
        super().__init__("database_manager")
        self.config = config
        self.context = context
        self.group_db_connections: Dict[str, aiosqlite.Connection] = {}
        self.skip_table_init = skip_table_init # 新增：跳过表初始化标志

        # 安全地构建路径
        if not config.data_dir:
            raise ValueError("config.data_dir 不能为空")

        self.group_data_dir = os.path.join(config.data_dir, "group_databases")
        self.messages_db_path = config.messages_db_path

        # 新增: 数据库后端（支持SQLite和MySQL）
        self.db_backend: Optional[IDatabaseBackend] = None

        # 新增: DatabaseEngine for ORM支持
        self.db_engine: Optional[DatabaseEngine] = None

        # 确保数据目录存在
        os.makedirs(self.group_data_dir, exist_ok=True)

        self._logger.info(f"数据库管理器初始化完成 (类型: {config.db_type}, 跳过表初始化: {skip_table_init})")

    async def _do_start(self) -> bool:
        """启动服务时初始化连接池和数据库"""
        try:
            self._logger.info(f" [DatabaseManager] 开始启动 (db_type={self.config.db_type}, skip_table_init={self.skip_table_init})")

            # 1. 创建数据库后端（无论 skip_table_init 是否为 True 都需要初始化后端）
            # skip_table_init 只影响表的创建，不影响后端连接的初始化
            self._logger.info(f" [DatabaseManager] 正在初始化 {self.config.db_type} 数据库后端...")
            backend_success = await self._initialize_database_backend()

            # 2. 如果数据库后端初始化失败，直接报错，不回退
            if not backend_success or not self.db_backend:
                error_msg = f" {self.config.db_type} 数据库后端初始化失败"
                self._logger.error(error_msg)
                raise RuntimeError(error_msg)

            self._logger.info(f" [DatabaseManager] {self.config.db_type} 后端初始化成功")

            # 3. 初始化数据库表结构（如果表不存在则自动创建）
            # 如果 skip_table_init=True（由 ORM 管理表），则跳过表创建
            if not self.skip_table_init:
                await self._init_messages_database()
                self._logger.info(" [DatabaseManager] 全局消息数据库初始化成功")
            else:
                self._logger.info(" [DatabaseManager] 跳过传统数据库表创建（由 SQLAlchemy ORM 管理）")

            self._logger.info(f" [DatabaseManager] 数据库管理器启动完成 (使用后端: {self.config.db_type})")
            return True
        except Exception as e:
            self._logger.error(f" [DatabaseManager] 启动数据库管理器失败: {e}", exc_info=True)
            return False

    async def _initialize_database_backend(self) -> bool:
        """初始化数据库后端"""
        try:
            # 构建数据库配置
            db_type = DatabaseType(self.config.db_type.lower())

            if db_type == DatabaseType.SQLITE:
                db_config = DatabaseConfig(
                    db_type=DatabaseType.SQLITE,
                    sqlite_path=self.messages_db_path,
                    max_connections=self.config.max_connections,
                    min_connections=self.config.min_connections
                )
            elif db_type == DatabaseType.MYSQL:
                db_config = DatabaseConfig(
                    db_type=DatabaseType.MYSQL,
                    mysql_host=self.config.mysql_host,
                    mysql_port=self.config.mysql_port,
                    mysql_user=self.config.mysql_user,
                    mysql_password=self.config.mysql_password,
                    mysql_database=self.config.mysql_database,
                    max_connections=self.config.max_connections,
                    min_connections=self.config.min_connections
                )
            elif db_type == DatabaseType.POSTGRESQL:
                db_config = DatabaseConfig(
                    db_type=DatabaseType.POSTGRESQL,
                    postgresql_host=self.config.postgresql_host,
                    postgresql_port=self.config.postgresql_port,
                    postgresql_user=self.config.postgresql_user,
                    postgresql_password=self.config.postgresql_password,
                    postgresql_database=self.config.postgresql_database,
                    postgresql_schema=self.config.postgresql_schema,
                    max_connections=self.config.max_connections,
                    min_connections=self.config.min_connections
                )
            else:
                raise ValueError(f"不支持的数据库类型: {self.config.db_type}")

            # 使用工厂创建后端
            self.db_backend = DatabaseFactory.create_backend(db_config)
            if not self.db_backend:
                raise Exception("创建数据库后端失败")

            # 初始化后端
            success = await self.db_backend.initialize()
            if not success:
                raise Exception("数据库后端初始化失败")

            self._logger.info(f"数据库后端初始化成功: {self.config.db_type}")
            return True

        except Exception as e:
            self._logger.error(f"初始化数据库后端失败: {e}", exc_info=True)
            return False

    async def _do_stop(self) -> bool:
        """停止服务时关闭所有数据库连接"""
        try:
            # 关闭数据库后端
            if self.db_backend:
                await self.db_backend.close()

            # 关闭 group 数据库连接
            await self.close_all_connections()

            self._logger.info("所有数据库连接已关闭")
            return True
        except Exception as e:
            self._logger.error(f"关闭数据库管理器失败: {e}", exc_info=True)
            return False

    def get_db_connection(self):
        """
        获取数据库连接的上下文管理器
        根据配置的数据库类型，自动选择SQLite、MySQL或PostgreSQL后端
        """
        db_type = self.config.db_type.lower()

        # 调试日志：输出数据库类型和后端状态
        self._logger.debug(f"[get_db_connection] 配置的数据库类型: {db_type}")
        self._logger.debug(f"[get_db_connection] db_backend 状态: {self.db_backend is not None}")

        # 统一通过数据库后端获取连接（SQLite/MySQL/PostgreSQL 共用路径）
        if self.db_backend:
            self._logger.debug(f"[get_db_connection] 使用 {db_type.upper()} 后端")
            return self._get_backend_connection_manager()
        else:
            raise RuntimeError(
                f"[get_db_connection] 数据库后端未初始化 (db_type={db_type})，"
                "请确保 DatabaseManager 已正确启动"
            )

    def _get_backend_connection_manager(self):
        """获取MySQL/PostgreSQL连接管理器 - 适配aiosqlite接口"""
        db_backend = self.db_backend

        class BackendConnectionAdapter:
            """数据库后端连接适配器 - 模拟aiosqlite接口"""
            def __init__(self, backend):
                self.backend = backend
                self._cursor = None

            async def cursor(self):
                """返回游标适配器"""
                return BackendCursorAdapter(self.backend)

            async def commit(self):
                """提交事务 - 后端在execute中已自动提交"""
                pass

            async def rollback(self):
                """回滚事务"""
                await self.backend.rollback()

            async def execute(self, sql, params=None):
                """执行SQL"""
                return await self.backend.execute(sql, params)

            async def executemany(self, sql, params_list):
                """批量执行SQL"""
                return await self.backend.execute_many(sql, params_list)

            async def fetchone(self):
                """获取单行"""
                return await self._cursor.fetchone() if self._cursor else None

            async def fetchall(self):
                """获取所有行"""
                return await self._cursor.fetchall() if self._cursor else []

        class BackendCursorAdapter:
            """数据库后端游标适配器"""
            def __init__(self, backend):
                self.backend = backend
                self._last_result = None
                self.lastrowid = None
                self.rowcount = 0

            async def execute(self, sql, params=None):
                """执行SQL并存储结果"""
                import re

                # 检测是SELECT查询还是其他操作
                sql_upper = sql.strip().upper()

                # 获取数据库类型
                db_type = self.backend.db_type
                is_mysql = (db_type == DatabaseType.MYSQL)
                is_postgresql = (db_type == DatabaseType.POSTGRESQL)

                # 对于 CREATE TABLE 和 ALTER TABLE，需要特殊处理
                if sql_upper.startswith('CREATE TABLE') or sql_upper.startswith('ALTER TABLE'):
                    # 使用后端的 convert_ddl 进行转换
                    converted_sql = self.backend.convert_ddl(sql)
                    await self.backend.execute(converted_sql, None)
                    self._last_result = []
                    self.rowcount = 0
                    return self

                # 转换参数占位符
                if is_mysql:
                    # MySQL: 转换 INSERT OR REPLACE 为 REPLACE INTO
                    converted_sql = sql.replace('INSERT OR REPLACE', 'REPLACE')
                    # 转换参数占位符 ? -> %s
                    converted_sql = converted_sql.replace('?', '%s')
                elif is_postgresql:
                    # PostgreSQL 使用 $1, $2, ...
                    # 调用后端的占位符转换方法
                    converted_sql = self.backend._convert_placeholders(sql) if hasattr(self.backend, '_convert_placeholders') else sql
                else:
                    converted_sql = sql

                # 确保 params 是 tuple 类型
                if params is not None and not isinstance(params, tuple):
                    if isinstance(params, list):
                        params = tuple(params)
                    else:
                        params = (params,)

                # 处理 sqlite_master 查询
                if 'SQLITE_MASTER' in sql_upper:
                    table_match = re.search(r"NAME\s*=\s*['\"]?(\w+)['\"]?", sql_upper)
                    if table_match:
                        table_name = table_match.group(1).lower()
                        if is_mysql:
                            check_sql = """
                                SELECT TABLE_NAME as name
                                FROM INFORMATION_SCHEMA.TABLES
                                WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = %s
                            """
                            self._last_result = await self.backend.fetch_all(check_sql, (table_name,))
                        elif is_postgresql:
                            check_sql = """
                                SELECT table_name as name
                                FROM information_schema.tables
                                WHERE table_schema = $1 AND LOWER(table_name) = $2
                            """
                            schema = getattr(self.backend.config, 'postgresql_schema', 'public')
                            self._last_result = await self.backend.fetch_all(check_sql, (schema, table_name))
                        self.rowcount = len(self._last_result) if self._last_result else 0
                        return self
                    else:
                        self._last_result = []
                        self.rowcount = 0
                        return self

                # 处理 PRAGMA table_info 查询
                if sql_upper.startswith('PRAGMA'):
                    pragma_match = re.search(r'PRAGMA\s+TABLE_INFO\s*\(\s*(\w+)\s*\)', sql_upper)
                    if pragma_match:
                        table_name = pragma_match.group(1)
                        try:
                            if is_mysql:
                                describe_sql = f"DESCRIBE {table_name}"
                                mysql_result = await self.backend.fetch_all(describe_sql, None)
                                self._last_result = []
                                for idx, row in enumerate(mysql_result or []):
                                    field_name = row[0]
                                    field_type = row[1]
                                    is_nullable = 0 if row[2] == 'NO' else 1
                                    default_value = row[4]
                                    is_pk = 1 if row[3] == 'PRI' else 0
                                    self._last_result.append((idx, field_name, field_type, 1 - is_nullable, default_value, is_pk))
                            elif is_postgresql:
                                # PostgreSQL 使用 information_schema.columns
                                schema = getattr(self.backend.config, 'postgresql_schema', 'public')
                                pg_sql = """
                                    SELECT
                                        ordinal_position - 1 as cid,
                                        column_name as name,
                                        data_type as type,
                                        CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END as notnull,
                                        column_default as dflt_value,
                                        0 as pk
                                    FROM information_schema.columns
                                    WHERE table_schema = $1 AND table_name = $2
                                    ORDER BY ordinal_position
                                """
                                self._last_result = await self.backend.fetch_all(pg_sql, (schema, table_name))
                            self.rowcount = len(self._last_result)
                        except Exception:
                            self._last_result = []
                            self.rowcount = 0
                        return self
                    else:
                        self._last_result = []
                        self.rowcount = 0
                        return self

                if sql_upper.startswith('SELECT'):
                    self._last_result = await self.backend.fetch_all(converted_sql, params)
                    self.rowcount = len(self._last_result) if self._last_result else 0
                else:
                    # INSERT/UPDATE/DELETE
                    self.rowcount = await self.backend.execute(converted_sql, params)
                    # 尝试获取lastrowid（对于INSERT操作）
                    if sql_upper.startswith('INSERT'):
                        try:
                            if is_mysql:
                                result = await self.backend.fetch_one("SELECT LAST_INSERT_ID()")
                            elif is_postgresql:
                                result = await self.backend.fetch_one("SELECT lastval()")
                            else:
                                result = None
                            self.lastrowid = result[0] if result else None
                        except Exception:
                            self.lastrowid = None
                return self

            async def executemany(self, sql, params_list):
                """批量执行SQL"""
                db_type = self.backend.db_type
                if db_type == DatabaseType.MYSQL:
                    converted_sql = sql.replace('?', '%s')
                elif db_type == DatabaseType.POSTGRESQL:
                    converted_sql = self.backend._convert_placeholders(sql) if hasattr(self.backend, '_convert_placeholders') else sql
                else:
                    converted_sql = sql
                self.rowcount = await self.backend.execute_many(converted_sql, params_list)
                return self

            async def fetchone(self):
                """获取单行结果"""
                if self._last_result and len(self._last_result) > 0:
                    return self._last_result[0]
                return None

            async def fetchall(self):
                """获取所有结果"""
                return self._last_result if self._last_result else []

            def __aiter__(self):
                """支持异步迭代"""
                self._iter_index = 0
                return self

            async def __anext__(self):
                """异步迭代"""
                if not self._last_result or self._iter_index >= len(self._last_result):
                    raise StopAsyncIteration
                result = self._last_result[self._iter_index]
                self._iter_index += 1
                return result

            async def close(self):
                """关闭游标（后端使用连接池，无需实际关闭）"""
                self._last_result = None
                self.lastrowid = None
                self.rowcount = 0

        class BackendConnectionManager:
            def __init__(self, backend):
                self.backend = backend
                self.adapter = None

            async def __aenter__(self):
                self.adapter = BackendConnectionAdapter(self.backend)
                return self.adapter

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                # 后端使用连接池，无需手动关闭
                pass

        return BackendConnectionManager(db_backend)

    def get_connection(self):
        """
        获取数据库连接的同步接口，用于兼容旧代码
        注意：这是一个同步方法，用于兼容使用 'with' 语句的代码
        """
        class SyncConnectionWrapper:
            def __init__(self, db_manager):
                self.db_manager = db_manager
                self.connection = None
                
            def __enter__(self):
                # 同步获取连接，这需要在异步上下文中使用
                import sqlite3
                # 直接创建同步连接到同一个数据库文件
                self.connection = sqlite3.connect(self.db_manager.messages_db_path)
                return self.connection
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.connection:
                    self.connection.close()
        
        return SyncConnectionWrapper(self)

    async def close_all_connections(self):
        """关闭所有数据库连接"""
        try:
            # 关闭所有群组数据库连接
            for group_id, conn in list(self.group_db_connections.items()):
                try:
                    await conn.close()
                    self._logger.info(f"群组 {group_id} 数据库连接已关闭")
                except Exception as e:
                    self._logger.error(f"关闭群组 {group_id} 数据库连接失败: {e}")
            
            self.group_db_connections.clear()
            self._logger.info("所有群组数据库连接已关闭")
            
        except Exception as e:
            self._logger.error(f"关闭数据库连接过程中发生错误: {e}")
            raise

    async def _init_messages_database(self):
        """
        初始化全局消息数据库（根据数据库类型选择后端）

         已废弃：所有表结构由 SQLAlchemy ORM 统一管理
        此方法保留仅用于向后兼容，不再创建表
        """
        self._logger.info(" [传统数据库管理器] 表创建已由 SQLAlchemy ORM 接管，跳过传统表初始化")
        # 如果使用MySQL后端，使用db_backend初始化表
        # if self.db_backend and self.config.db_type.lower() == 'mysql':
        # await self._init_messages_database_mysql()
        # self._logger.info("MySQL数据库表初始化完成。")
        # else:
        # # 使用旧的SQLite连接池
        # async with self.get_db_connection() as conn:
        # await self._init_messages_database_tables(conn)
        # self._logger.info("全局消息数据库连接池初始化完成并表已初始化。")

    def get_group_db_path(self, group_id: str) -> str:
        """获取群数据库文件路径"""
        if not group_id:
            raise ValueError("group_id 不能为空")
        if not self.group_data_dir:
            raise ValueError("group_data_dir 未初始化")
        return os.path.join(self.group_data_dir, f"{group_id}_ID.db")

    async def get_group_connection(self, group_id: str) -> aiosqlite.Connection:
        """获取群数据库连接"""
        if group_id not in self.group_db_connections:
            db_path = self.get_group_db_path(group_id)
            
            # 确保数据库目录存在
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)
            
            # 检查数据库文件权限
            if os.path.exists(db_path):
                try:
                    # 尝试修改文件权限为可写
                    import stat
                    os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
                except OSError as e:
                    logger.warning(f"无法修改群数据库文件权限: {e}")
            
            conn = await aiosqlite.connect(db_path)
            
            # 设置连接参数，确保数据库可写
            await conn.execute('PRAGMA foreign_keys = ON')
            await conn.execute('PRAGMA journal_mode = WAL') 
            await conn.execute('PRAGMA synchronous = NORMAL')
            await conn.commit()
            
            await self._init_group_database(conn)
            self.group_db_connections[group_id] = conn
            logger.info(f"已创建群 {group_id} 的数据库连接")
        
        return self.group_db_connections[group_id]

    async def _init_group_database(self, conn: aiosqlite.Connection):
        """初始化群数据库表结构"""
        cursor = await conn.cursor()
        
        try:
            # 设置数据库为WAL模式，提高并发性能并避免锁定问题
            await cursor.execute('PRAGMA journal_mode=WAL')
            await cursor.execute('PRAGMA synchronous=NORMAL')
            await cursor.execute('PRAGMA cache_size=10000')
            await cursor.execute('PRAGMA temp_store=memory')
            
            # 原始消息表 (群数据库中不再存储原始消息，由全局消息数据库统一管理)
            # 筛选消息表 (群数据库中不再存储筛选消息，由全局消息数据库统一管理)
            
            # 用户画像表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS user_profiles (
                    qq_id TEXT PRIMARY KEY,
                    qq_name TEXT,
                    nicknames TEXT, -- JSON格式存储
                    activity_pattern TEXT, -- JSON格式存储活动模式
                    communication_style TEXT, -- JSON格式存储沟通风格
                    topic_preferences TEXT, -- JSON格式存储话题偏好
                    emotional_tendency TEXT, -- JSON格式存储情感倾向
                    last_active REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 社交关系表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS social_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    relation_type TEXT NOT NULL, -- mention, reply, frequent_interaction
                    strength REAL NOT NULL,
                    frequency INTEGER NOT NULL,
                    last_interaction REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(from_user, to_user, relation_type)
                )
            ''')
            
            # 风格档案表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS style_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL,
                    vocabulary_richness REAL,
                    sentence_complexity REAL,
                    emotional_expression REAL,
                    interaction_tendency REAL,
                    topic_diversity REAL,
                    formality_level REAL,
                    creativity_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 人格备份表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS persona_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    reason TEXT,
                    persona_config TEXT, -- JSON格式存储人格配置
                    original_persona TEXT, -- JSON格式存储
                    imitation_dialogues TEXT, -- JSON格式存储模仿对话
                    backup_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 风格学习记录表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS style_learning_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    style_type TEXT NOT NULL,
                    learned_patterns TEXT, -- JSON格式存储学习到的模式
                    confidence_score REAL,
                    sample_count INTEGER,
                    last_updated REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 情感表达模式表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS emotion_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emotional_pattern TEXT NOT NULL,
                    confidence_score REAL,
                    frequency INTEGER DEFAULT 0,
                    context_type TEXT,
                    last_updated REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 语言风格模式表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS language_style_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    language_style TEXT NOT NULL,
                    example_phrases TEXT, -- JSON格式存储示例短语
                    usage_frequency INTEGER DEFAULT 0,
                    context_type TEXT DEFAULT 'general',
                    confidence_score REAL,
                    last_updated REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 主题偏好表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS topic_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_category TEXT NOT NULL,
                    interest_level REAL,
                    response_style TEXT,
                    sample_count INTEGER DEFAULT 0,
                    confidence_score REAL,
                    last_updated REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 人格更新审查表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS persona_update_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_type TEXT NOT NULL, -- style_update, persona_update, learning_update
                    original_content TEXT, -- 原始人格内容
                    proposed_content TEXT, -- 建议的新内容
                    confidence_score REAL,
                    reason TEXT, -- 更新原因
                    sample_messages TEXT, -- JSON格式存储触发更新的示例消息
                    review_status TEXT DEFAULT 'pending', -- pending, approved, rejected
                    reviewer_comment TEXT,
                    created_at REAL,
                    reviewed_at REAL,
                    auto_score REAL, -- 自动评分
                    manual_override BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # 学习批次表 (如果不存在)
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS learning_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_name TEXT,
                    start_time REAL,
                    end_time REAL,
                    processed_messages INTEGER DEFAULT 0,
                    success BOOLEAN DEFAULT FALSE,
                    error_message TEXT,
                    learning_type TEXT, -- style_learning, persona_update, etc.
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 学习会话表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS learning_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    messages_processed INTEGER DEFAULT 0,
                    filtered_messages INTEGER DEFAULT 0,
                    style_updates INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 0.0,
                    success BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_social_relations_from_user ON social_relations(from_user)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_social_relations_to_user ON social_relations(to_user)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(last_active)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_style_profiles_name ON style_profiles(profile_name)')
            
            # 创建好感度表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS user_affection (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    affection_level INTEGER DEFAULT 0,
                    last_interaction REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    interaction_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            # 创建bot情绪表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_mood (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    mood_type TEXT NOT NULL,
                    mood_intensity REAL DEFAULT 0.5,
                    mood_description TEXT,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建好感度变化记录表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS affection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    change_amount INTEGER NOT NULL,
                    previous_level INTEGER NOT NULL,
                    new_level INTEGER NOT NULL,
                    change_reason TEXT,
                    bot_mood TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.commit() 
            logger.debug("群数据库表结构初始化完成") 
            
        except aiosqlite.Error as e: 
            logger.error(f"初始化群数据库失败: {e}", exc_info=True) 
            raise DataStorageError(f"初始化群数据库失败: {str(e)}")

    async def save_style_profile(self, group_id: str, profile_data: Dict[str, Any]):
        """保存风格档案到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO style_profiles
                (profile_name, vocabulary_richness, sentence_complexity, emotional_expression,
                 interaction_tendency, topic_diversity, formality_level, creativity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                profile_data['profile_name'],
                profile_data.get('vocabulary_richness'),
                profile_data.get('sentence_complexity'),
                profile_data.get('emotional_expression'),
                profile_data.get('interaction_tendency'),
                profile_data.get('topic_diversity'),
                profile_data.get('formality_level'),
                profile_data.get('creativity_score')
            ))
            await conn.commit()
            logger.debug(f"风格档案 '{profile_data['profile_name']}' 已保存到群 {group_id} 数据库。")
        except aiosqlite.Error as e:
            logger.error(f"保存风格档案失败: {e}", exc_info=True)
            raise DataStorageError(f"保存风格档案失败: {str(e)}")

    async def load_style_profile(self, group_id: str, profile_name: str) -> Optional[Dict[str, Any]]:
        """从数据库加载风格档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                SELECT profile_name, vocabulary_richness, sentence_complexity, emotional_expression,
                       interaction_tendency, topic_diversity, formality_level, creativity_score
                FROM style_profiles WHERE profile_name = ?
            ''', (profile_name,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'profile_name': row[0],
                'vocabulary_richness': row[1],
                'sentence_complexity': row[2],
                'emotional_expression': row[3],
                'interaction_tendency': row[4],
                'topic_diversity': row[5],
                'formality_level': row[6],
                'creativity_score': row[7]
            }
        except aiosqlite.Error as e:
            logger.error(f"加载风格档案失败: {e}", exc_info=True)
            return None

    async def save_user_profile(self, group_id: str, profile_data: Dict[str, Any]):
        """保存用户画像到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO user_profiles 
                (qq_id, qq_name, nicknames, activity_pattern, communication_style, 
                 topic_preferences, emotional_tendency, last_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                profile_data['qq_id'],
                profile_data.get('qq_name', ''),
                json.dumps(profile_data.get('nicknames', []), ensure_ascii=False),
                json.dumps(profile_data.get('activity_pattern', {}), ensure_ascii=False),
                json.dumps(profile_data.get('communication_style', {}), ensure_ascii=False),
                json.dumps(profile_data.get('topic_preferences', {}), ensure_ascii=False),
                json.dumps(profile_data.get('emotional_tendency', {}), ensure_ascii=False),
                profile_data.get('last_active', time.time()), # 使用profile中的值或当前时间
                datetime.now().isoformat()
            ))
            
            await conn.commit()
            
        except aiosqlite.Error as e:
            logger.error(f"保存用户画像失败: {e}", exc_info=True)
            raise DataStorageError(f"保存用户画像失败: {str(e)}")

    async def load_user_profile(self, group_id: str, qq_id: str) -> Optional[Dict[str, Any]]:
        """从数据库加载用户画像"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT qq_id, qq_name, nicknames, activity_pattern, communication_style,
                       topic_preferences, emotional_tendency, last_active
                FROM user_profiles WHERE qq_id = ?
            ''', (qq_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            return {
                'qq_id': row[0],
                'qq_name': row[1],
                'nicknames': json.loads(row[2]) if row[2] else [],
                'activity_pattern': json.loads(row[3]) if row[3] else {},
                'communication_style': json.loads(row[4]) if row[4] else {},
                'topic_preferences': json.loads(row[5]) if row[5] else {},
                'emotional_tendency': json.loads(row[6]) if row[6] else {},
                'last_active': row[7]
            }
            
        except aiosqlite.Error as e:
            logger.error(f"加载用户画像失败: {e}", exc_info=True)
            return None

    async def save_social_relation(self, group_id: str, relation_data: Dict[str, Any]):
        """保存社交关系到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO social_relations
                (from_user, to_user, relation_type, strength, frequency, last_interaction, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                relation_data['from_user'],
                relation_data['to_user'],
                relation_data['relation_type'],
                relation_data['strength'],
                relation_data['frequency'],
                relation_data['last_interaction'],
                datetime.now().isoformat()
            ))

            await conn.commit()

        except aiosqlite.Error as e:
            logger.error(f"保存社交关系失败: {e}", exc_info=True)
            raise DataStorageError(f"保存社交关系失败: {str(e)}")

    async def get_social_relations_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """获取指定群组的社交关系"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            # 添加 WHERE 子句来过滤特定群组的关系
            # 社交关系中的 from_user 和 to_user 格式为 "group_id:user_id"
            await cursor.execute('''
                SELECT from_user, to_user, relation_type, strength, frequency, last_interaction
                FROM social_relations
                WHERE (from_user LIKE ? OR to_user LIKE ?)
                ORDER BY frequency DESC, strength DESC
            ''', (f'{group_id}:%', f'{group_id}:%'))

            rows = await cursor.fetchall()
            relations = []

            for row in rows:
                try:
                    # 添加行数据验证
                    if len(row) < 6:
                        self._logger.warning(f"社交关系数据行不完整 (期望6个字段，实际{len(row)}个)，跳过: {row}")
                        continue

                    relations.append({
                        'from_user': row[0],
                        'to_user': row[1],
                        'relation_type': row[2],
                        'strength': float(row[3]) if row[3] else 0.0,
                        'frequency': int(row[4]) if row[4] else 0,
                        'last_interaction': row[5]
                    })
                except Exception as row_error:
                    self._logger.warning(f"处理社交关系数据行时出错，跳过: {row_error}, row: {row}")

            self._logger.info(f"群组 {group_id} 加载了 {len(relations)} 条社交关系")
            return relations

        except aiosqlite.Error as e:
            logger.error(f"获取社交关系失败: {e}", exc_info=True)
            return []

    async def get_user_social_relations(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取指定用户在群组中的社交关系

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            包含用户社交关系的字典，包括：
            - outgoing: 该用户发起的关系列表
            - incoming: 指向该用户的关系列表
            - total_relations: 总关系数
        """
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            user_key = f"{group_id}:{user_id}"

            # 获取该用户发起的关系（outgoing）
            await cursor.execute('''
                SELECT from_user, to_user, relation_type, strength, frequency, last_interaction
                FROM social_relations
                WHERE from_user = ? OR from_user = ?
                ORDER BY frequency DESC, strength DESC
                LIMIT 10
            ''', (user_key, user_id))

            outgoing_rows = await cursor.fetchall()
            outgoing_relations = []

            for row in outgoing_rows:
                outgoing_relations.append({
                    'from_user': row[0],
                    'to_user': row[1],
                    'relation_type': row[2],
                    'strength': row[3],
                    'frequency': row[4],
                    'last_interaction': row[5]
                })

            # 获取指向该用户的关系（incoming）
            await cursor.execute('''
                SELECT from_user, to_user, relation_type, strength, frequency, last_interaction
                FROM social_relations
                WHERE to_user = ? OR to_user = ?
                ORDER BY frequency DESC, strength DESC
                LIMIT 10
            ''', (user_key, user_id))

            incoming_rows = await cursor.fetchall()
            incoming_relations = []

            for row in incoming_rows:
                incoming_relations.append({
                    'from_user': row[0],
                    'to_user': row[1],
                    'relation_type': row[2],
                    'strength': row[3],
                    'frequency': row[4],
                    'last_interaction': row[5]
                })

            return {
                'user_id': user_id,
                'group_id': group_id,
                'outgoing': outgoing_relations,
                'incoming': incoming_relations,
                'total_relations': len(outgoing_relations) + len(incoming_relations)
            }

        except aiosqlite.Error as e:
            logger.error(f"获取用户社交关系失败: {e}", exc_info=True)
            return {
                'user_id': user_id,
                'group_id': group_id,
                'outgoing': [],
                'incoming': [],
                'total_relations': 0
            }


    async def save_raw_message(self, message_data) -> int:
        """
        将原始消息保存到全局消息数据库。
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 检查message_data是否为字典或对象
                if hasattr(message_data, 'sender_id'):
                    # 如果是对象，直接访问属性
                    await cursor.execute('''
                        INSERT INTO raw_messages (sender_id, sender_name, message, group_id, platform, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        message_data.sender_id,
                        message_data.sender_name,
                        message_data.message,
                        message_data.group_id,
                        message_data.platform,
                        message_data.timestamp
                    ))
                else:
                    # 如果是字典，使用字典访问
                    await cursor.execute('''
                        INSERT INTO raw_messages (sender_id, sender_name, message, group_id, platform, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        message_data.get('sender_id'),
                        message_data.get('sender_name'),
                        message_data.get('message'),
                        message_data.get('group_id'),
                        message_data.get('platform'),
                        message_data.get('timestamp')
                    ))
                
                message_id = cursor.lastrowid
                await conn.commit()
                logger.info(f" 数据库写入成功: ID={message_id}, timestamp={message_data.timestamp if hasattr(message_data, 'timestamp') else message_data.get('timestamp')}")
                return message_id
                
            except aiosqlite.Error as e:
                logger.error(f"保存原始消息失败: {e}", exc_info=True)
                raise DataStorageError(f"保存原始消息失败: {str(e)}")
            finally:
                await cursor.close()

    async def get_unprocessed_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取未处理的原始消息

        Args:
            limit: 限制返回的消息数量

        Returns:
            未处理的消息列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                if limit:
                    await cursor.execute('''
                        SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                        FROM raw_messages
                        WHERE processed = FALSE
                        ORDER BY timestamp ASC
                        LIMIT ?
                    ''', (limit,))
                else:
                    await cursor.execute('''
                        SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                        FROM raw_messages
                        WHERE processed = FALSE
                        ORDER BY timestamp ASC
                    ''')

                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2],
                        'message': row[3],
                        'group_id': row[4],
                        'platform': row[5],
                        'timestamp': row[6]
                    })

                logger.debug(f"获取到 {len(messages)} 条未处理消息")
                return messages

            except aiosqlite.Error as e:
                logger.error(f"获取未处理消息失败: {e}", exc_info=True)
                raise DataStorageError(f"获取未处理消息失败: {str(e)}")
            finally:
                await cursor.close()

    async def mark_messages_processed(self, message_ids: List[int]) -> bool:
        """
        标记消息为已处理

        Args:
            message_ids: 消息ID列表

        Returns:
            是否成功标记
        """
        if not message_ids:
            return True

        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 批量更新消息状态
                placeholders = ','.join(['?' for _ in message_ids])
                await cursor.execute(f'''
                    UPDATE raw_messages
                    SET processed = TRUE
                    WHERE id IN ({placeholders})
                ''', message_ids)

                await conn.commit()
                logger.debug(f"已标记 {len(message_ids)} 条消息为已处理")
                return True

            except aiosqlite.Error as e:
                logger.error(f"标记消息处理状态失败: {e}", exc_info=True)
                raise DataStorageError(f"标记消息处理状态失败: {str(e)}")
            finally:
                await cursor.close()

    async def add_filtered_message(self, filtered_data: Dict[str, Any]) -> int:
        """
        添加筛选后的消息
        
        Args:
            filtered_data: 筛选后的消息数据
            
        Returns:
            筛选消息的ID
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                current_time = int(time.time())
                await cursor.execute('''
                    INSERT INTO filtered_messages
                    (raw_message_id, message, sender_id, confidence, filter_reason, timestamp, quality_scores, group_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    filtered_data.get('raw_message_id'),
                    filtered_data.get('message'),
                    filtered_data.get('sender_id'),
                    filtered_data.get('confidence', 0.8),
                    filtered_data.get('filter_reason', ''),
                    filtered_data.get('timestamp') or current_time,
                    json.dumps(filtered_data.get('quality_scores', {}), ensure_ascii=False),
                    filtered_data.get('group_id'),
                    current_time
                ))
                
                filtered_id = cursor.lastrowid
                await conn.commit()
                logger.debug(f"筛选消息已保存，ID: {filtered_id}")
                return filtered_id
                
            except aiosqlite.Error as e:
                logger.error(f"添加筛选消息失败: {e}", exc_info=True)
                raise DataStorageError(f"添加筛选消息失败: {str(e)}")
            finally:
                await cursor.close()

    async def get_filtered_messages_for_learning(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取用于学习的筛选消息
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            筛选消息列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                if limit:
                    await cursor.execute('''
                        SELECT id, message, sender_id, confidence, quality_scores, timestamp, group_id
                        FROM filtered_messages 
                        WHERE used_for_learning = FALSE 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    ''', (limit,))
                else:
                    await cursor.execute('''
                        SELECT id, message, sender_id, confidence, quality_scores, timestamp, group_id
                        FROM filtered_messages 
                        WHERE used_for_learning = FALSE 
                        ORDER BY timestamp DESC
                    ''')
                
                messages = []
                for row in await cursor.fetchall():
                    try:
                        # 添加行数据验证
                        if len(row) < 7:
                            self._logger.warning(f"筛选消息行数据不完整 (期望7个字段，实际{len(row)}个)，跳过: {row}")
                            continue

                        quality_scores = {}
                        try:
                            if row[4]: # quality_scores
                                quality_scores = json.loads(row[4])
                        except (json.JSONDecodeError, TypeError):
                            pass

                        messages.append({
                            'id': row[0],
                            'message': row[1],
                            'sender_id': row[2],
                            'confidence': float(row[3]) if row[3] else 0.0,
                            'quality_scores': quality_scores,
                            'timestamp': float(row[5]) if row[5] else 0,
                            'group_id': row[6]
                        })
                    except Exception as row_error:
                        self._logger.warning(f"处理筛选消息行时出错，跳过: {row_error}, row: {row if len(row) < 20 else 'too long'}")

                return messages
                
            except aiosqlite.Error as e:
                logger.error(f"获取学习消息失败: {e}", exc_info=True)
                raise DataStorageError(f"获取学习消息失败: {str(e)}")
            finally:
                await cursor.close()

    async def get_recent_filtered_messages(self, group_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取指定群组最近的筛选消息
        
        Args:
            group_id: 群组ID
            limit: 消息数量限制
            
        Returns:
            筛选消息列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                await cursor.execute('''
                    SELECT id, message, sender_id, confidence, quality_scores, timestamp
                    FROM filtered_messages 
                    WHERE group_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (group_id, limit))
                
                messages = []
                for row in await cursor.fetchall():
                    quality_scores = {}
                    try:
                        if row[4]:
                            quality_scores = json.loads(row[4])
                    except json.JSONDecodeError:
                        pass
                        
                    messages.append({
                        'id': row[0],
                        'message': row[1],
                        'sender_id': row[2],
                        'confidence': row[3],
                        'quality_scores': quality_scores,
                        'timestamp': row[5]
                    })
                    
                return messages
                
            except aiosqlite.Error as e:
                logger.error(f"获取最近筛选消息失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_recent_raw_messages(self, group_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        """
        获取指定群组最近的原始消息，用于表达风格学习
        
        Args:
            group_id: 群组ID
            limit: 消息数量限制
            
        Returns:
            原始消息列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                await cursor.execute('''
                    SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                    FROM raw_messages 
                    WHERE group_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (group_id, limit))
                
                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2],
                        'message': row[3],
                        'group_id': row[4],
                        'platform': row[5],
                        'timestamp': row[6]
                    })
                    
                return messages
                
            except aiosqlite.Error as e:
                logger.error(f"获取最近原始消息失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_messages_statistics(self) -> Dict[str, Any]:
        """
        获取消息统计信息

        Returns:
            统计信息字典
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 获取原始消息统计
                await cursor.execute('SELECT COUNT(*) FROM raw_messages')
                result = await cursor.fetchone()
                if not result or len(result) == 0:
                    total_messages = 0
                else:
                    total_messages = int(result[0]) if result[0] and str(result[0]).isdigit() else 0

                await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE processed = FALSE')
                result = await cursor.fetchone()
                unprocessed_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                # 获取筛选消息统计
                await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
                result = await cursor.fetchone()
                filtered_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE used_for_learning = FALSE')
                result = await cursor.fetchone()
                unused_filtered_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                stats = {
                    'total_messages': total_messages,
                    'unprocessed_messages': unprocessed_messages,
                    'filtered_messages': filtered_messages,
                    'unused_filtered_messages': unused_filtered_messages,
                    'raw_messages': total_messages # 兼容旧接口
                }

                # 验证返回的统计数据没有表名
                for key, value in stats.items():
                    if isinstance(value, str) and not value.replace('-', '').isdigit():
                        self._logger.error(f"get_messages_statistics 返回了非数字字符串: {key}={value}，设置为0")
                        stats[key] = 0

                return stats

            except aiosqlite.Error as e:
                self._logger.error(f"获取消息统计失败: {e}", exc_info=True)
                return {
                    'total_messages': 0,
                    'unprocessed_messages': 0,
                    'filtered_messages': 0,
                    'unused_filtered_messages': 0,
                    'raw_messages': 0
                }
            finally:
                await cursor.close()

    async def get_pending_style_reviews(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取待审查的风格学习记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_pending_style_reviews_orm(limit)
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 确保表存在
                await self._ensure_style_review_table_exists(cursor)
                
                await cursor.execute('''
                    SELECT id, type, group_id, timestamp, learned_patterns, few_shots_content, 
                           status, description, created_at
                    FROM style_learning_reviews
                    WHERE status = 'pending'
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
                reviews = []
                for row in await cursor.fetchall():
                    learned_patterns = []
                    try:
                        if row[4]: # learned_patterns
                            learned_patterns = json.loads(row[4])
                    except json.JSONDecodeError:
                        pass
                        
                    reviews.append({
                        'id': row[0],
                        'type': row[1],
                        'group_id': row[2],
                        'timestamp': row[3],
                        'learned_patterns': learned_patterns,
                        'few_shots_content': row[5],
                        'status': row[6],
                        'description': row[7],
                        'created_at': row[8]
                    })
                
                return reviews
                
            except Exception as e:
                self._logger.error(f"获取待审查风格学习记录失败: {e}")
                return []
            finally:
                await cursor.close()

    async def get_reviewed_style_learning_updates(self, limit: int = 50, offset: int = 0, status_filter: str = None) -> List[Dict[str, Any]]:
        """获取已审查的风格学习记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_reviewed_style_learning_updates_orm(limit, offset, status_filter)
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 确保表存在
                await self._ensure_style_review_table_exists(cursor)
                
                # 构建查询条件
                where_clause = "WHERE status != 'pending'"
                params = []
                
                if status_filter:
                    where_clause += " AND status = ?"
                    params.append(status_filter)
                
                params.extend([limit, offset])
                
                await cursor.execute(f'''
                    SELECT id, type, group_id, timestamp, learned_patterns, few_shots_content, 
                           status, description, created_at, updated_at
                    FROM style_learning_reviews
                    {where_clause}
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                ''', params)
                
                reviews = []
                for row in await cursor.fetchall():
                    learned_patterns = []
                    try:
                        if row[4]: # learned_patterns
                            learned_patterns = json.loads(row[4])
                    except json.JSONDecodeError:
                        pass
                        
                    reviews.append({
                        'id': row[0],
                        'type': row[1],
                        'group_id': row[2],
                        'timestamp': row[3],
                        'learned_patterns': learned_patterns,
                        'few_shots_content': row[5],
                        'status': row[6],
                        'description': row[7],
                        'created_at': row[8],
                        'review_time': row[9] if len(row) > 9 else None
                    })
                
                return reviews
                
            except Exception as e:
                self._logger.error(f"获取已审查风格学习记录失败: {e}")
                return []
            finally:
                await cursor.close()

    async def get_detailed_metrics(self) -> Dict[str, Any]:
        """获取详细监控数据"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                detailed_data = {
                    'api_metrics': {
                        'hours': list(range(24)),
                        'response_times': [100 + i * 10 for i in range(24)]
                    },
                    'database_metrics': {
                        'table_stats': {}
                    },
                    'system_metrics': {
                        'memory_percent': 45.2,
                        'cpu_percent': 23.1,
                        'disk_percent': 67.8
                    },
                    'connection_pool_stats': {
                        'total_connections': 0,
                        'active_connections': 0,
                        'max_connections': self.config.max_connections,
                        'pool_usage': 0
                    }
                }
                
                # 获取数据库表统计
                try:
                    tables = ['raw_messages', 'filtered_messages', 'expression_patterns']
                    for table in tables:
                        try:
                            await cursor.execute(f'SELECT COUNT(*) FROM {table}')
                            count = (await cursor.fetchone())[0]
                            detailed_data['database_metrics']['table_stats'][table] = {'count': count}
                        except Exception:
                            detailed_data['database_metrics']['table_stats'][table] = {'count': 0}
                            
                except Exception as e:
                    self._logger.warning(f"获取数据库表统计失败: {e}")
                
                return detailed_data
                
            except Exception as e:
                self._logger.error(f"获取详细监控数据失败: {e}")
                return {
                    'api_metrics': {'hours': [], 'response_times': []},
                    'database_metrics': {'table_stats': {}},
                    'system_metrics': {'memory_percent': 0, 'cpu_percent': 0, 'disk_percent': 0},
                    'connection_pool_stats': {'total_connections': 0, 'active_connections': 0, 'max_connections': 0, 'pool_usage': 0}
                }
            finally:
                await cursor.close()

    async def get_message_statistics(self, group_id: str = None) -> Dict[str, Any]:
        """获取消息统计信息，兼容 webui.py 的调用"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                if group_id:
                    # 获取特定群组的统计
                    await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ?', (group_id,))
                    total_messages = (await cursor.fetchone())[0]
                    
                    await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ? AND processed = FALSE', (group_id,))
                    unprocessed_messages = (await cursor.fetchone())[0]
                    
                    await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ?', (group_id,))
                    filtered_messages = (await cursor.fetchone())[0]
                    
                    await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ? AND used_for_learning = FALSE', (group_id,))
                    unused_filtered_messages = (await cursor.fetchone())[0]
                else:
                    # 获取全局统计
                    return await self.get_messages_statistics()
                
                return {
                    'total_messages': total_messages,
                    'unprocessed_messages': unprocessed_messages,
                    'filtered_messages': filtered_messages,
                    'unused_filtered_messages': unused_filtered_messages,
                    'raw_messages': total_messages,
                    'group_id': group_id
                }
                
            except aiosqlite.Error as e:
                self._logger.error(f"获取消息统计失败: {e}", exc_info=True)
                return {
                    'total_messages': 0,
                    'unprocessed_messages': 0,
                    'filtered_messages': 0,
                    'unused_filtered_messages': 0,
                    'raw_messages': 0,
                    'group_id': group_id
                }
            finally:
                await cursor.close()

    async def get_recent_learning_batches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的学习批次记录"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 确保表存在
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS learning_batches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL,
                        batch_name TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL,
                        quality_score REAL,
                        processed_messages INTEGER DEFAULT 0,
                        message_count INTEGER DEFAULT 0,
                        filtered_count INTEGER DEFAULT 0,
                        success BOOLEAN DEFAULT FALSE,
                        error_message TEXT
                    )
                ''')
                
                await cursor.execute('''
                    SELECT group_id, batch_name, start_time, end_time, quality_score,
                           processed_messages, message_count, filtered_count, success, error_message
                    FROM learning_batches 
                    ORDER BY start_time DESC 
                    LIMIT ?
                ''', (limit,))
                
                batches = []
                for row in await cursor.fetchall():
                    batches.append({
                        'group_id': row[0],
                        'batch_name': row[1],
                        'start_time': row[2],
                        'end_time': row[3],
                        'quality_score': row[4] or 0,
                        'processed_messages': row[5] or 0,
                        'message_count': row[6] or 0,
                        'filtered_count': row[7] or 0,
                        'success': bool(row[8]),
                        'error_message': row[9]
                    })
                
                return batches
                
            except Exception as e:
                self._logger.error(f"获取最近学习批次失败: {e}")
                return []
            finally:
                await cursor.close()

    async def get_style_progress_data(self) -> List[Dict[str, Any]]:
        """获取风格进度数据"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 首先检查表是否存在
                await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='learning_batches'")
                if not await cursor.fetchone():
                    self._logger.info("learning_batches 表不存在，返回空列表")
                    return []

                # 从学习批次中获取进度数据，包含消息数量信息
                # 只显示有实际消息的记录（过滤旧的空数据）
                await cursor.execute('''
                    SELECT group_id, start_time, quality_score, success,
                           processed_messages, filtered_count, batch_name
                    FROM learning_batches
                    WHERE quality_score IS NOT NULL
                      AND processed_messages > 0
                    ORDER BY start_time DESC
                    LIMIT 30
                ''')

                progress_data = []
                rows = await cursor.fetchall()

                self._logger.debug(f"get_style_progress_data 获取到 {len(rows)} 行数据")
                if rows and len(rows) > 0:
                    self._logger.debug(f"第一行数据: {rows[0]}, 列数: {len(rows[0])}")

                for row in rows:
                    try:
                        # 添加行数据验证（现在有7个字段）
                        if len(row) < 4:
                            self._logger.warning(f"学习批次进度数据行不完整 (期望至少4个字段，实际{len(row)}个)，跳过: {row}")
                            continue

                        progress_item = {
                            'group_id': row[0],
                            'timestamp': float(row[1]) if row[1] else 0,
                            'quality_score': float(row[2]) if row[2] else 0,
                            'success': bool(row[3])
                        }

                        # 添加消息数量信息（如果存在）
                        if len(row) > 4:
                            progress_item['processed_messages'] = int(row[4]) if row[4] else 0
                        if len(row) > 5:
                            progress_item['filtered_count'] = int(row[5]) if row[5] else 0
                        if len(row) > 6:
                            progress_item['batch_name'] = row[6] if row[6] else '未命名'

                        progress_data.append(progress_item)
                    except Exception as row_error:
                        self._logger.warning(f"处理学习批次进度数据行时出错，跳过: {row_error}, row: {row}")

                return progress_data

            except Exception as e:
                self._logger.warning(f"从learning_batches表获取进度数据失败: {e}")
                return []
            finally:
                await cursor.close()

    async def get_style_learning_statistics(self) -> Dict[str, Any]:
        """获取风格学习统计数据"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                stats = {
                    'unique_styles': 0,
                    'avg_confidence': 0,
                    'total_samples': 0,
                    'latest_update': None
                }
                
                # 从表达模式表获取统计
                try:
                    await cursor.execute('SELECT COUNT(*) FROM expression_patterns')
                    stats['total_samples'] = (await cursor.fetchone())[0] or 0

                    await cursor.execute('SELECT AVG(weight), MAX(create_time) FROM expression_patterns')
                    row = await cursor.fetchone()
                    if row[0]:
                        stats['avg_confidence'] = round((row[0] or 0) * 100, 1)
                    
                    if row[1]:
                        stats['latest_update'] = datetime.fromtimestamp(row[1]).strftime('%Y-%m-%d %H:%M')
                    
                    # 计算独特风格数量（基于群组）
                    await cursor.execute('SELECT COUNT(DISTINCT group_id) FROM expression_patterns')
                    stats['unique_styles'] = (await cursor.fetchone())[0] or 0
                    
                except Exception as e:
                    self._logger.warning(f"从expression_patterns表获取统计失败: {e}")
                
                return stats
                
            except Exception as e:
                self._logger.error(f"获取风格学习统计失败: {e}")
                return {
                    'unique_styles': 0,
                    'avg_confidence': 0,
                    'total_samples': 0,
                    'latest_update': None
                }
            finally:
                await cursor.close()

    async def get_group_messages_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取指定群组的消息统计信息

        Args:
            group_id: 群组ID

        Returns:
            统计信息字典
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 获取原始消息统计
                await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ?', (group_id,))
                result = await cursor.fetchone()
                total_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ? AND processed = FALSE', (group_id,))
                result = await cursor.fetchone()
                unprocessed_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                # 获取筛选消息统计
                await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ?', (group_id,))
                result = await cursor.fetchone()
                filtered_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ? AND used_for_learning = FALSE', (group_id,))
                result = await cursor.fetchone()
                unused_filtered_messages = int(result[0]) if result and result[0] and str(result[0]).replace('-', '').isdigit() else 0

                stats = {
                    'total_messages': total_messages,
                    'unprocessed_messages': unprocessed_messages,
                    'filtered_messages': filtered_messages,
                    'unused_filtered_messages': unused_filtered_messages,
                    'raw_messages': total_messages # 兼容旧接口
                }

                # 验证返回的统计数据没有表名
                for key, value in stats.items():
                    if isinstance(value, str) and not value.replace('-', '').isdigit():
                        self._logger.error(f"get_group_messages_statistics 返回了非数字字符串: {key}={value}，设置为0")
                        stats[key] = 0

                return stats

            except aiosqlite.Error as e:
                logger.error(f"获取群组消息统计失败: {e}", exc_info=True)
                return {
                    'total_messages': 0,
                    'unprocessed_messages': 0,
                    'filtered_messages': 0,
                    'unused_filtered_messages': 0,
                    'raw_messages': 0
                }
            finally:
                await cursor.close()

    async def load_social_graph(self, group_id: str) -> List[Dict[str, Any]]:
        """加载完整社交图谱"""
        self._logger.debug(f"[数据库] 开始加载群组 {group_id} 的社交图谱")
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                SELECT from_user, to_user, relation_type, strength, frequency, last_interaction
                FROM social_relations ORDER BY strength DESC
            ''')

            relations = []
            for row in await cursor.fetchall():
                relations.append({
                    'from_user': row[0],
                    'to_user': row[1],
                    'relation_type': row[2],
                    'strength': row[3],
                    'frequency': row[4],
                    'last_interaction': row[5]
                })

            self._logger.info(f"[数据库] 成功加载群组 {group_id} 的社交图谱: {len(relations)} 条关系记录")
            if len(relations) == 0:
                self._logger.warning(f"[数据库] 警告: 群组 {group_id} 的social_relations表中没有数据!")
            else:
                # 输出前3条示例
                self._logger.debug(f"[数据库] 社交关系示例: {relations[:3]}")

            return relations

        except aiosqlite.Error as e:
            self._logger.error(f"[数据库] 加载社交图谱失败 (群组: {group_id}): {e}", exc_info=True)
            return []

    async def get_messages_for_replay(self, group_id: str, days: int, limit: int) -> List[Dict[str, Any]]:
        """
        从全局消息数据库获取指定群组在过去一段时间内的原始消息，用于记忆重放。
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                start_timestamp = time.time() - (days * 86400) # 转换为秒
                
                await cursor.execute('''
                    SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                    FROM raw_messages 
                    WHERE group_id = ? AND timestamp > ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (group_id, start_timestamp, limit))
                
                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2],
                        'message': row[3],
                        'group_id': row[4],
                        'platform': row[5],
                        'timestamp': row[6]
                    })
                
                return messages
                
            except aiosqlite.Error as e:
                self._logger.error(f"获取记忆重放消息失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def backup_persona(self, group_id: str, backup_data: Dict[str, Any]) -> int:
        """备份人格数据"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 获取当前时间戳
            current_timestamp = time.time()
            
            await cursor.execute(''' 
                INSERT INTO persona_backups (backup_name, timestamp, original_persona, imitation_dialogues, backup_reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                backup_data['backup_name'],
                current_timestamp,
                json.dumps(backup_data['original_persona'], ensure_ascii=False),
                json.dumps(backup_data.get('imitation_dialogues', []), ensure_ascii=False),
                backup_data.get('backup_reason', 'Auto backup before update')
            ))
            
            backup_id = cursor.lastrowid
            await conn.commit()
            
            logger.info(f"人格数据已备份，备份ID: {backup_id}")
            return backup_id
            
        except aiosqlite.Error as e:
            logger.error(f"备份人格数据失败: {e}", exc_info=True)
            raise DataStorageError(f"备份人格数据失败: {str(e)}")

    async def get_persona_backups(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的人格备份"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT id, backup_name, created_at FROM persona_backups 
                ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            
            backups = []
            for row in await cursor.fetchall():
                backups.append({
                    'id': row[0],
                    'backup_name': row[1],
                    'created_at': row[2]
                })
            
            return backups
            
        except aiosqlite.Error as e:
            logger.error(f"获取人格备份失败: {e}", exc_info=True)
            return []

    async def restore_persona(self, group_id: str, backup_id: int) -> Optional[Dict[str, Any]]:
        """从备份恢复人格数据"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT backup_name, original_persona, imitation_dialogues, backup_reason 
                FROM persona_backups WHERE id = ?
            ''', (backup_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            return {
                'backup_name': row[0],
                'original_persona': json.loads(row[1]),
                'imitation_dialogues': json.loads(row[2]),
                'backup_reason': row[3]
            }
            
        except aiosqlite.Error as e:
            logger.error(f"恢复人格数据失败: {e}", exc_info=True)
            return None

    async def save_persona_update_record(self, record: Dict[str, Any]) -> int:
        """保存人格更新记录到数据库"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                await cursor.execute('''
                    INSERT INTO persona_update_records (timestamp, group_id, update_type, original_content, new_content, reason, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('timestamp', time.time()),
                    record.get('group_id'),
                    record.get('update_type'),
                    record.get('original_content'),
                    record.get('new_content'),
                    record.get('reason'),
                    record.get('status', 'pending')
                ))
                
                record_id = cursor.lastrowid
                await conn.commit()
                logger.debug(f"人格更新记录已保存，ID: {record_id}")
                return record_id
                
            except aiosqlite.Error as e:
                logger.error(f"保存人格更新记录失败: {e}", exc_info=True)
                raise DataStorageError(f"保存人格更新记录失败: {str(e)}")
            finally:
                await cursor.close()

    async def get_pending_persona_update_records(self) -> List[Dict[str, Any]]:
        """获取所有待审查的人格更新记录"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 首先检查表是否存在以及包含什么数据
                await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='persona_update_records'")
                if not await cursor.fetchone():
                    self._logger.info("persona_update_records 表不存在")
                    return []
                
                # 检查表中总共有多少记录
                await cursor.execute('SELECT COUNT(*) FROM persona_update_records')
                total_count = (await cursor.fetchone())[0]
                self._logger.info(f"persona_update_records 表中总共有 {total_count} 条记录")
                
                # 检查各种状态的记录数量
                await cursor.execute('SELECT status, COUNT(*) FROM persona_update_records GROUP BY status')
                status_counts = await cursor.fetchall()
                self._logger.info(f"各状态记录数量: {dict(status_counts)}")
                
                # 优先查询pending状态的记录
                await cursor.execute('''
                    SELECT id, timestamp, group_id, update_type, original_content, new_content, reason, status, reviewer_comment, review_time
                    FROM persona_update_records
                    WHERE status = 'pending'
                    ORDER BY timestamp DESC
                ''')
                
                records = []
                pending_rows = await cursor.fetchall()
                self._logger.info(f"找到 {len(pending_rows)} 条pending状态的记录")
                
                for row in pending_rows:
                    records.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'group_id': row[2],
                        'update_type': row[3],
                        'original_content': row[4],
                        'new_content': row[5],
                        'reason': row[6],
                        'status': row[7],
                        'reviewer_comment': row[8],
                        'review_time': row[9]
                    })
                
                # 如果没有pending状态的记录，尝试查询所有记录（可能status字段为空或其他值）
                if not records and total_count > 0:
                    self._logger.info("没有pending状态记录，查询所有记录...")
                    await cursor.execute('''
                        SELECT id, timestamp, group_id, update_type, original_content, new_content, reason, 
                               COALESCE(status, 'pending') as status, reviewer_comment, review_time
                        FROM persona_update_records
                        WHERE status IS NULL OR status = '' OR status = 'pending'
                        ORDER BY timestamp DESC
                        LIMIT 50
                    ''')
                    
                    all_rows = await cursor.fetchall()
                    self._logger.info(f"找到 {len(all_rows)} 条可能的待审查记录")
                    
                    for row in all_rows:
                        records.append({
                            'id': row[0],
                            'timestamp': row[1],
                            'group_id': row[2],
                            'update_type': row[3],
                            'original_content': row[4],
                            'new_content': row[5],
                            'reason': row[6],
                            'status': 'pending', # 强制设置为pending
                            'reviewer_comment': row[8],
                            'review_time': row[9]
                        })
                
                return records
                
            except aiosqlite.Error as e:
                logger.error(f"获取待审查人格更新记录失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def update_persona_update_record_status(self, record_id: int, status: str, reviewer_comment: Optional[str] = None) -> bool:
        """更新人格更新记录的状态"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                review_time = time.time()
                await cursor.execute('''
                    UPDATE persona_update_records
                    SET status = ?, reviewer_comment = ?, review_time = ?
                    WHERE id = ?
                ''', (status, reviewer_comment, review_time, record_id))
                
                await conn.commit()
                logger.debug(f"人格更新记录 {record_id} 状态已更新为 {status}")
                return cursor.rowcount > 0
                
            except aiosqlite.Error as e:
                logger.error(f"更新人格更新记录状态失败: {e}", exc_info=True)
                raise DataStorageError(f"更新人格更新记录状态失败: {str(e)}")
            finally:
                await cursor.close()

    async def delete_persona_update_record(self, record_id: int) -> bool:
        """删除人格更新记录"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                await cursor.execute('''
                    DELETE FROM persona_update_records
                    WHERE id = ?
                ''', (record_id,))
                
                await conn.commit()
                logger.debug(f"人格更新记录 {record_id} 已删除")
                return cursor.rowcount > 0
                
            except aiosqlite.Error as e:
                logger.error(f"删除人格更新记录失败: {e}", exc_info=True)
                raise DataStorageError(f"删除人格更新记录失败: {str(e)}")
            finally:
                await cursor.close()

    async def get_persona_update_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取人格更新记录"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    SELECT id, timestamp, group_id, update_type, original_content, new_content, reason, status, reviewer_comment, review_time
                    FROM persona_update_records
                    WHERE id = ?
                ''', (record_id,))

                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'timestamp': row[1],
                        'group_id': row[2],
                        'update_type': row[3],
                        'original_content': row[4],
                        'new_content': row[5],
                        'reason': row[6],
                        'status': row[7],
                        'reviewer_comment': row[8],
                        'review_time': row[9]
                    }
                return None

            except aiosqlite.Error as e:
                logger.error(f"获取人格更新记录失败: {e}", exc_info=True)
                return None
            finally:
                await cursor.close()

    # 高级功能数据库操作方法

    async def save_emotion_profile(self, group_id: str, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """保存情感档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS emotion_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    dominant_emotions TEXT, -- JSON格式
                    emotion_patterns TEXT, -- JSON格式
                    empathy_level REAL DEFAULT 0.5,
                    emotional_stability REAL DEFAULT 0.5,
                    last_updated REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO emotion_profiles 
                (user_id, group_id, dominant_emotions, emotion_patterns, empathy_level, emotional_stability, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                group_id,
                json.dumps(profile_data.get('dominant_emotions', {}), ensure_ascii=False),
                json.dumps(profile_data.get('emotion_patterns', {}), ensure_ascii=False),
                profile_data.get('empathy_level', 0.5),
                profile_data.get('emotional_stability', 0.5),
                profile_data.get('last_updated', time.time())
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存情感档案失败: {e}")
            return False

    async def load_emotion_profile(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """加载情感档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT dominant_emotions, emotion_patterns, empathy_level, emotional_stability, last_updated
                FROM emotion_profiles WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'user_id': user_id,
                'group_id': group_id,
                'dominant_emotions': json.loads(row[0]) if row[0] else {},
                'emotion_patterns': json.loads(row[1]) if row[1] else {},
                'empathy_level': row[2],
                'emotional_stability': row[3],
                'last_updated': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"加载情感档案失败: {e}")
            return None

    async def save_knowledge_entity(self, group_id: str, entity_data: Dict[str, Any]) -> bool:
        """保存知识实体"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    attributes TEXT, -- JSON格式
                    relationships TEXT, -- JSON格式
                    confidence REAL DEFAULT 0.5,
                    source_messages TEXT, -- JSON格式
                    last_mentioned REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO knowledge_entities 
                (entity_id, name, entity_type, attributes, relationships, confidence, source_messages, last_mentioned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entity_data.get('entity_id'),
                entity_data.get('name', ''),
                entity_data.get('entity_type', 'unknown'),
                json.dumps(entity_data.get('attributes', {}), ensure_ascii=False),
                json.dumps(entity_data.get('relationships', []), ensure_ascii=False),
                entity_data.get('confidence', 0.5),
                json.dumps(entity_data.get('source_messages', []), ensure_ascii=False),
                entity_data.get('last_mentioned', time.time())
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存知识实体失败: {e}")
            return False

    async def get_knowledge_entities(self, group_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取知识实体列表"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT entity_id, name, entity_type, attributes, relationships, confidence, source_messages, last_mentioned
                FROM knowledge_entities 
                ORDER BY last_mentioned DESC
                LIMIT ?
            ''', (limit,))
            
            entities = []
            for row in await cursor.fetchall():
                entities.append({
                    'entity_id': row[0],
                    'name': row[1],
                    'entity_type': row[2],
                    'attributes': json.loads(row[3]) if row[3] else {},
                    'relationships': json.loads(row[4]) if row[4] else [],
                    'confidence': row[5],
                    'source_messages': json.loads(row[6]) if row[6] else [],
                    'last_mentioned': row[7]
                })
            
            return entities
            
        except Exception as e:
            self._logger.error(f"获取知识实体失败: {e}")
            return []

    # 新增强化学习相关方法
    async def save_reinforcement_learning_result(self, group_id: str, result_data: Dict[str, Any]) -> bool:
        """保存强化学习结果"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                await cursor.execute('''
                    INSERT INTO reinforcement_learning_results 
                    (group_id, timestamp, replay_analysis, optimization_strategy, reinforcement_feedback, next_action)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    group_id,
                    result_data.get('timestamp', time.time()),
                    json.dumps(result_data.get('replay_analysis', {}), ensure_ascii=False),
                    json.dumps(result_data.get('optimization_strategy', {}), ensure_ascii=False),
                    json.dumps(result_data.get('reinforcement_feedback', {}), ensure_ascii=False),
                    result_data.get('next_action', '')
                ))
                
                await conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"保存强化学习结果失败: {e}")
                return False
            finally:
                await cursor.close()

    async def get_learning_history_for_reinforcement(self, group_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取用于强化学习的历史数据"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT timestamp, quality_score, success, successful_pattern, failed_pattern
                FROM learning_performance_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'timestamp': row[0],
                    'quality_score': row[1],
                    'success': bool(row[2]),
                    'successful_pattern': row[3] or '',
                    'failed_pattern': row[4] or ''
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取强化学习历史数据失败: {e}")
            return []
        finally:
            await cursor.close()

    async def save_persona_fusion_result(self, group_id: str, fusion_data: Dict[str, Any]) -> bool:
        """保存人格融合结果"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO persona_fusion_history 
                (group_id, timestamp, base_persona_hash, incremental_hash, fusion_result, compatibility_score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                fusion_data.get('timestamp', time.time()),
                fusion_data.get('base_persona_hash'),
                fusion_data.get('incremental_hash'),
                json.dumps(fusion_data.get('fusion_result', {}), ensure_ascii=False),
                fusion_data.get('compatibility_score', 0.0)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存人格融合结果失败: {e}")
            return False
        finally:
            await cursor.close()

    async def get_persona_fusion_history(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取人格融合历史"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT timestamp, base_persona_hash, incremental_hash, fusion_result, compatibility_score
                FROM persona_fusion_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                fusion_result = {}
                try:
                    fusion_result = json.loads(row[3]) if row[3] else {}
                except json.JSONDecodeError:
                    logger.warning(f"解析融合结果JSON失败: {row[3]}")
                
                history.append({
                    'timestamp': row[0],
                    'base_persona_hash': row[1],
                    'incremental_hash': row[2],
                    'fusion_result': fusion_result,
                    'compatibility_score': row[4]
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取人格融合历史失败: {e}")
            return []
        finally:
            await cursor.close()

    async def save_strategy_optimization_result(self, group_id: str, optimization_data: Dict[str, Any]) -> bool:
        """保存策略优化结果"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO strategy_optimization_results 
                (group_id, timestamp, original_strategy, optimization_result, expected_improvement)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                group_id,
                optimization_data.get('timestamp', time.time()),
                json.dumps(optimization_data.get('original_strategy', {}), ensure_ascii=False),
                json.dumps(optimization_data.get('optimization_result', {}), ensure_ascii=False),
                json.dumps(optimization_data.get('expected_improvement', {}), ensure_ascii=False)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存策略优化结果失败: {e}")
            return False
        finally:
            await cursor.close()

    async def get_learning_performance_history(self, group_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """获取学习性能历史数据"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT session_id, timestamp, quality_score, learning_time, success
                FROM learning_performance_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'session_id': row[0],
                    'timestamp': row[1],
                    'quality_score': row[2] or 0.0,
                    'learning_time': row[3] or 0.0,
                    'success': bool(row[4])
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取学习性能历史失败: {e}")
            return []
        finally:
            await cursor.close()

    async def save_learning_performance_record(self, group_id: str, performance_data: Dict[str, Any]) -> bool:
        """保存学习性能记录"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO learning_performance_history 
                (group_id, session_id, timestamp, quality_score, learning_time, success, successful_pattern, failed_pattern)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                performance_data.get('session_id', ''),
                performance_data.get('timestamp', time.time()),
                performance_data.get('quality_score', 0.0),
                performance_data.get('learning_time', 0.0),
                performance_data.get('success', False),
                performance_data.get('successful_pattern', ''),
                performance_data.get('failed_pattern', '')
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存学习性能记录失败: {e}")
            return False
        finally:
            await cursor.close()

    async def get_messages_for_replay(self, group_id: str, days: int = 30, limit: int = 100) -> List[Dict[str, Any]]:
        """获取用于记忆重放的消息"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()
            
            try:
                # 获取指定天数内的消息
                cutoff_time = time.time() - (days * 24 * 3600)
                
                await cursor.execute('''
                    SELECT id, message, sender_id, group_id, timestamp
                    FROM raw_messages 
                    WHERE group_id = ? AND timestamp > ? AND processed = TRUE
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (group_id, cutoff_time, limit))
                
                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'message_id': row[0],
                        'message': row[1],
                        'sender_id': row[2],
                        'group_id': row[3],
                        'timestamp': row[4]
                    })
                
                return messages
                
            except Exception as e:
                logger.error(f"获取记忆重放消息失败: {e}")
                return []
            finally:
                await cursor.close()

    async def save_user_preferences(self, group_id: str, user_id: str, preferences: Dict[str, Any]) -> bool:
        """保存用户偏好设置"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    favorite_topics TEXT, -- JSON格式
                    interaction_style TEXT, -- JSON格式
                    learning_preferences TEXT, -- JSON格式
                    adaptive_rate REAL DEFAULT 0.5,
                    updated_at REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, group_id, favorite_topics, interaction_style, learning_preferences, adaptive_rate, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                group_id,
                json.dumps(preferences.get('favorite_topics', []), ensure_ascii=False),
                json.dumps(preferences.get('interaction_style', {}), ensure_ascii=False),
                json.dumps(preferences.get('learning_preferences', {}), ensure_ascii=False),
                preferences.get('adaptive_rate', 0.5),
                time.time()
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存用户偏好失败: {e}")
            return False

    async def load_user_preferences(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """加载用户偏好设置"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT favorite_topics, interaction_style, learning_preferences, adaptive_rate, updated_at
                FROM user_preferences WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'favorite_topics': json.loads(row[0]) if row[0] else [],
                'interaction_style': json.loads(row[1]) if row[1] else {},
                'learning_preferences': json.loads(row[2]) if row[2] else {},
                'adaptive_rate': row[3],
                'updated_at': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"加载用户偏好失败: {e}")
            return None

    async def save_conversation_context(self, group_id: str, context_data: Dict[str, Any]) -> bool:
        """保存对话上下文"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    context_id TEXT UNIQUE NOT NULL,
                    participants TEXT, -- JSON格式存储参与者列表
                    current_topic TEXT,
                    emotion_state TEXT, -- JSON格式存储情感状态
                    context_messages TEXT, -- JSON格式存储上下文消息
                    start_time REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO conversation_contexts 
                (group_id, context_id, participants, current_topic, emotion_state, context_messages, start_time, last_updated, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                context_data.get('context_id'),
                json.dumps(list(context_data.get('participants', set())), ensure_ascii=False),
                context_data.get('current_topic'),
                json.dumps(context_data.get('emotion_state', {}), ensure_ascii=False),
                json.dumps(context_data.get('messages', []), ensure_ascii=False),
                context_data.get('start_time', time.time()),
                time.time(),
                context_data.get('is_active', True)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存对话上下文失败: {e}")
            return False

    async def get_active_conversation_contexts(self, group_id: str) -> List[Dict[str, Any]]:
        """获取活跃的对话上下文"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT context_id, participants, current_topic, emotion_state, context_messages, start_time, last_updated
                FROM conversation_contexts 
                WHERE group_id = ? AND is_active = TRUE
                ORDER BY last_updated DESC
            ''', (group_id,))
            
            contexts = []
            for row in await cursor.fetchall():
                contexts.append({
                    'context_id': row[0],
                    'participants': set(json.loads(row[1])) if row[1] else set(),
                    'current_topic': row[2],
                    'emotion_state': json.loads(row[3]) if row[3] else {},
                    'messages': json.loads(row[4]) if row[4] else [],
                    'start_time': row[5],
                    'last_updated': row[6]
                })
            
            return contexts
            
        except Exception as e:
            self._logger.error(f"获取对话上下文失败: {e}")
            return []

    async def save_learning_session_record(self, group_id: str, session_data: Dict[str, Any]) -> bool:
        """保存学习会话记录"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO learning_sessions
                (session_id, start_time, end_time, messages_processed, filtered_messages, 
                 style_updates, quality_score, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data.get('session_id'),
                session_data.get('start_time'),
                session_data.get('end_time'),
                session_data.get('messages_processed', 0),
                session_data.get('filtered_messages', 0),
                session_data.get('style_updates', 0),
                session_data.get('quality_score', 0.0),
                session_data.get('success', False)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存学习会话记录失败: {e}")
            return False

    async def get_recent_learning_sessions(self, group_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近的学习会话记录"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            start_time = time.time() - (days * 24 * 3600)
            
            await cursor.execute('''
                SELECT session_id, start_time, end_time, messages_processed, filtered_messages,
                       style_updates, quality_score, success
                FROM learning_sessions 
                WHERE start_time >= ?
                ORDER BY start_time DESC
            ''', (start_time,))
            
            sessions = []
            for row in await cursor.fetchall():
                sessions.append({
                    'session_id': row[0],
                    'start_time': row[1],
                    'end_time': row[2],
                    'messages_processed': row[3],
                    'filtered_messages': row[4],
                    'style_updates': row[5],
                    'quality_score': row[6],
                    'success': row[7]
                })
            
            return sessions
            
        except Exception as e:
            self._logger.error(f"获取学习会话记录失败: {e}")
            return []

    # 好感度系统数据库操作方法

    async def get_user_affection(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT affection_level, last_interaction, last_updated, interaction_count
                FROM user_affection WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'user_id': user_id,
                'group_id': group_id,
                'affection_level': row[0],
                'last_interaction': row[1],
                'last_updated': row[2],
                'interaction_count': row[3]
            }
            
        except Exception as e:
            self._logger.error(f"获取用户好感度失败: {e}")
            return None

    async def update_user_affection(self, group_id: str, user_id: str, 
                                  new_level: int, change_reason: str = "", 
                                  bot_mood: str = "") -> bool:
        """更新用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            
            # 获取当前好感度
            current_affection = await self.get_user_affection(group_id, user_id)
            previous_level = current_affection['affection_level'] if current_affection else 0
            interaction_count = current_affection['interaction_count'] if current_affection else 0
            
            # 更新或插入好感度记录
            await cursor.execute('''
                INSERT OR REPLACE INTO user_affection 
                (user_id, group_id, affection_level, last_interaction, last_updated, interaction_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, group_id, new_level, current_time, current_time, interaction_count + 1))
            
            # 记录好感度变化历史
            change_amount = new_level - previous_level
            if change_amount != 0:
                await cursor.execute('''
                    INSERT INTO affection_history 
                    (user_id, group_id, change_amount, previous_level, new_level, 
                     change_reason, bot_mood, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, group_id, change_amount, previous_level, new_level, 
                      change_reason, bot_mood, current_time))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"更新用户好感度失败: {e}")
            return False

    async def get_all_user_affections(self, group_id: str) -> List[Dict[str, Any]]:
        """获取群内所有用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT user_id, affection_level, last_interaction, last_updated, interaction_count
                FROM user_affection 
                WHERE group_id = ?
                ORDER BY affection_level DESC
            ''', (group_id,))
            
            affections = []
            for row in await cursor.fetchall():
                affections.append({
                    'user_id': row[0],
                    'group_id': group_id,
                    'affection_level': row[1],
                    'last_interaction': row[2],
                    'last_updated': row[3],
                    'interaction_count': row[4]
                })
            
            return affections
            
        except Exception as e:
            self._logger.error(f"获取所有用户好感度失败: {e}")
            return []

    async def get_total_affection(self, group_id: str) -> int:
        """获取群内总好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT SUM(affection_level) FROM user_affection WHERE group_id = ?
            ''', (group_id,))
            
            result = await cursor.fetchone()
            return result[0] if result[0] is not None else 0
            
        except Exception as e:
            self._logger.error(f"获取总好感度失败: {e}")
            return 0

    async def save_bot_mood(self, group_id: str, mood_type: str, mood_intensity: float,
                           mood_description: str, duration_hours: int = 24) -> bool:
        """保存bot情绪状态"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            end_time = current_time + (duration_hours * 3600)
            
            # 将之前的情绪设为非活跃状态
            await cursor.execute('''
                UPDATE bot_mood SET is_active = FALSE, end_time = ? WHERE group_id = ? AND is_active = TRUE
            ''', (current_time, group_id))
            
            # 插入新的情绪状态
            await cursor.execute('''
                INSERT INTO bot_mood 
                (group_id, mood_type, mood_intensity, mood_description, start_time, end_time, is_active)
                VALUES (?, ?, ?, ?, ?, ?, TRUE)
            ''', (group_id, mood_type, mood_intensity, mood_description, current_time, end_time))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存bot情绪失败: {e}")
            return False

    async def get_current_bot_mood(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前bot情绪"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            
            await cursor.execute('''
                SELECT mood_type, mood_intensity, mood_description, start_time, end_time
                FROM bot_mood 
                WHERE group_id = ? AND is_active = TRUE AND start_time <= ? AND (end_time IS NULL OR end_time > ?)
                ORDER BY start_time DESC
                LIMIT 1
            ''', (group_id, current_time, current_time))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'mood_type': row[0],
                'mood_intensity': row[1],
                'mood_description': row[2],
                'start_time': row[3],
                'end_time': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"获取当前bot情绪失败: {e}")
            return None

    async def get_affection_history(self, group_id: str, user_id: str = None, 
                                   days: int = 7) -> List[Dict[str, Any]]:
        """获取好感度变化历史"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            start_time = time.time() - (days * 24 * 3600)
            
            if user_id:
                await cursor.execute('''
                    SELECT user_id, change_amount, previous_level, new_level, 
                           change_reason, bot_mood, timestamp
                    FROM affection_history 
                    WHERE group_id = ? AND user_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (group_id, user_id, start_time))
            else:
                await cursor.execute('''
                    SELECT user_id, change_amount, previous_level, new_level, 
                           change_reason, bot_mood, timestamp
                    FROM affection_history 
                    WHERE group_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (group_id, start_time))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'user_id': row[0],
                    'change_amount': row[1],
                    'previous_level': row[2],
                    'new_level': row[3],
                    'change_reason': row[4],
                    'bot_mood': row[5],
                    'timestamp': row[6]
                })
            
            return history
            
        except Exception as e:
            self._logger.error(f"获取好感度历史失败: {e}")
            return []

    async def record_llm_call_statistics(self, provider_type: str, model_name: str, 
                                        success: bool, response_time_ms: int) -> bool:
        """记录LLM调用统计数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                current_time = time.time()
                
                # 查询当前统计数据
                await cursor.execute('''
                    SELECT total_calls, success_calls, failed_calls, total_response_time_ms
                    FROM llm_call_statistics 
                    WHERE provider_type = ? AND model_name = ?
                ''', (provider_type, model_name))
                
                row = await cursor.fetchone()
                if row:
                    # 更新现有记录
                    total_calls = row[0] + 1
                    success_calls = row[1] + (1 if success else 0)
                    failed_calls = row[2] + (0 if success else 1)
                    total_response_time = row[3] + response_time_ms
                    avg_response_time = total_response_time / total_calls
                    success_rate = success_calls / total_calls
                    
                    await cursor.execute('''
                        UPDATE llm_call_statistics 
                        SET total_calls = ?, success_calls = ?, failed_calls = ?, 
                            total_response_time_ms = ?, avg_response_time_ms = ?, 
                            success_rate = ?, last_call_time = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE provider_type = ? AND model_name = ?
                    ''', (total_calls, success_calls, failed_calls, total_response_time,
                          avg_response_time, success_rate, current_time, provider_type, model_name))
                else:
                    # 插入新记录
                    success_calls = 1 if success else 0
                    failed_calls = 0 if success else 1
                    success_rate = 1.0 if success else 0.0
                    
                    await cursor.execute('''
                        INSERT INTO llm_call_statistics 
                        (provider_type, model_name, total_calls, success_calls, failed_calls,
                         total_response_time_ms, avg_response_time_ms, success_rate, last_call_time)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
                    ''', (provider_type, model_name, success_calls, failed_calls,
                          response_time_ms, response_time_ms, success_rate, current_time))
                
                await conn.commit()
                return True
                
        except Exception as e:
            self._logger.error(f"记录LLM调用统计失败: {e}")
            return False
        finally:
            await cursor.close()

    async def get_llm_call_statistics(self) -> Dict[str, Any]:
        """获取LLM调用统计数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                await cursor.execute('''
                    SELECT provider_type, model_name, total_calls, success_calls, failed_calls,
                           avg_response_time_ms, success_rate, last_call_time
                    FROM llm_call_statistics
                    ORDER BY provider_type, total_calls DESC
                ''')
                
                statistics = {}
                total_calls = 0
                
                for row in await cursor.fetchall():
                    provider_type = row[0]
                    model_name = row[1] or f"{provider_type}_model"
                    
                    stats = {
                        "total_calls": row[2],
                        "success_calls": row[3], 
                        "failed_calls": row[4],
                        "avg_response_time_ms": row[5] or 0,
                        "success_rate": row[6] or 0,
                        "last_call_time": row[7]
                    }
                    
                    statistics[f"{provider_type}_{model_name}"] = stats
                    total_calls += row[2]
                
                # 如果没有统计数据，返回默认结构
                if not statistics:
                    statistics = {
                        "filter_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0},
                        "refine_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0}, 
                        "reinforce_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0}
                    }
                
                return {
                    "statistics": statistics,
                    "total_calls": total_calls
                }
                
        except Exception as e:
            self._logger.error(f"获取LLM调用统计失败: {e}")
            return {
                "statistics": {
                    "filter_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0},
                    "refine_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0},
                    "reinforce_provider": {"total_calls": 0, "avg_response_time_ms": 0, "success_rate": 0, "error_count": 0}
                },
                "total_calls": 0
            }
        finally:
            await cursor.close()

    async def export_messages_learning_data(self) -> Dict[str, Any]:
        """导出消息学习数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

            # 导出原始消息
            await cursor.execute('''
                SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                FROM raw_messages ORDER BY timestamp DESC
            ''')
            raw_messages = []
            for row in await cursor.fetchall():
                raw_messages.append({
                    'id': row[0],
                    'sender_id': row[1],
                    'sender_name': row[2],
                    'message': row[3],
                    'group_id': row[4],
                    'platform': row[5],
                    'timestamp': row[6],
                    'processed': bool(row[7])
                })

            # 导出筛选消息
            await cursor.execute('''
                SELECT id, raw_message_id, message, sender_id, group_id, confidence,
                       filter_reason, timestamp, used_for_learning, quality_scores
                FROM filtered_messages ORDER BY timestamp DESC
            ''')
            filtered_messages = []
            for row in await cursor.fetchall():
                quality_scores = {}
                try:
                    if row[9]: # quality_scores
                        quality_scores = json.loads(row[9])
                except (json.JSONDecodeError, TypeError):
                    pass

                filtered_messages.append({
                    'id': row[0],
                    'raw_message_id': row[1],
                    'message': row[2],
                    'sender_id': row[3],
                    'group_id': row[4],
                    'confidence': row[5],
                    'filter_reason': row[6],
                    'timestamp': row[7],
                    'used_for_learning': bool(row[8]),
                    'quality_scores': quality_scores
                })

            # 导出学习批次记录
            await cursor.execute('''
                SELECT id, group_id, start_time, end_time, quality_score,
                       processed_messages, batch_name, message_count,
                       filtered_count, success, error_message
                FROM learning_batches ORDER BY start_time DESC
            ''')
            learning_batches = []
            for row in await cursor.fetchall():
                learning_batches.append({
                    'id': row[0],
                    'group_id': row[1],
                    'start_time': row[2],
                    'end_time': row[3],
                    'quality_score': row[4],
                    'processed_messages': row[5],
                    'batch_name': row[6],
                    'message_count': row[7],
                    'filtered_count': row[8],
                    'success': bool(row[9]),
                    'error_message': row[10]
                })

            # 导出人格更新记录
            await cursor.execute('''
                SELECT id, timestamp, group_id, update_type, original_content,
                       new_content, reason, status, reviewer_comment, review_time
                FROM persona_update_records ORDER BY timestamp DESC
            ''')
            persona_update_records = []
            for row in await cursor.fetchall():
                persona_update_records.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'group_id': row[2],
                    'update_type': row[3],
                    'original_content': row[4],
                    'new_content': row[5],
                    'reason': row[6],
                    'status': row[7],
                    'reviewer_comment': row[8],
                    'review_time': row[9]
                })

            # 获取统计信息
            statistics = await self.get_messages_statistics()

            export_data = {
                'export_timestamp': time.time(),
                'export_date': datetime.now().isoformat(),
                'statistics': statistics,
                'raw_messages': raw_messages,
                'filtered_messages': filtered_messages,
                'learning_batches': learning_batches,
                'persona_update_records': persona_update_records
            }

            self._logger.info(f"成功导出学习数据: {len(raw_messages)} 条原始消息, {len(filtered_messages)} 条筛选消息")
            return export_data

        except Exception as e:
            self._logger.error(f"导出消息学习数据失败: {e}", exc_info=True)
            raise DataStorageError(f"导出消息学习数据失败: {str(e)}")
        finally:
            await cursor.close()

    async def clear_all_messages_data(self):
        """清空所有消息数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

            # 清空所有表的数据
            tables_to_clear = [
                'raw_messages',
                'filtered_messages',
                'learning_batches',
                'persona_update_records',
                'reinforcement_learning_results',
                'persona_fusion_history',
                'strategy_optimization_results',
                'learning_performance_history'
            ]

            for table in tables_to_clear:
                await cursor.execute(f'DELETE FROM {table}')
                self._logger.debug(f"已清空表: {table}")

            await conn.commit()
            self._logger.info("所有消息数据已清空")

        except Exception as e:
            self._logger.error(f"清空所有消息数据失败: {e}", exc_info=True)
            raise DataStorageError(f"清空所有消息数据失败: {str(e)}")
        finally:
            await cursor.close()

    async def get_learning_patterns_data(self) -> Dict[str, Any]:
        """获取学习模式数据"""
        try:
            # 首先尝试获取表达模式数据（来自expression_patterns表）
            expression_patterns = await self.get_expression_patterns_for_webui()
            
            # 获取其他学习数据
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # 检查是否有原始消息数据
            await cursor.execute('SELECT COUNT(*) FROM raw_messages')
            raw_data_count = (await cursor.fetchone())[0]
            
            # 检查是否有筛选消息数据
            await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
            filtered_data_count = (await cursor.fetchone())[0]
            
            # 如果有表达模式数据，使用它；否则使用默认提示
            if expression_patterns:
                emotion_patterns = []
                for pattern in expression_patterns[:10]: # 显示前10个
                    situation = pattern.get('situation', '场景描述').strip()
                    expression = pattern.get('expression', '表达方式').strip()
                    weight = pattern.get('weight', 0)
                    
                    # 确保不显示空的或无意义的数据
                    if situation and expression and situation != '未知' and expression != '未知':
                        pattern_name = f"情感表达-{situation[:10]}" # 截取前10个字符作为模式名
                        emotion_patterns.append({
                            'pattern': pattern_name,
                            'confidence': round(weight * 20, 2), # 将权重转换为置信度百分比
                            'frequency': max(1, int(weight)) # 确保频率至少为1
                        })
                
                # 如果没有有效的表达模式，添加一个说明
                if not emotion_patterns:
                    emotion_patterns.append({
                        'pattern': '正在学习表达模式',
                        'confidence': 30.0,
                        'frequency': 1
                    })
            else:
                # 如果没有表达模式，但有原始数据，显示学习中状态
                if raw_data_count > 0:
                    emotion_patterns = [{
                        'pattern': '正在学习表达模式，请稍候...',
                        'confidence': 50.0,
                        'frequency': raw_data_count
                    }]
                else:
                    emotion_patterns = [{
                        'pattern': '暂无对话数据，请先进行对话',
                        'confidence': 0.0,
                        'frequency': 0
                    }]
            
            # 语言风格分析（基于原始消息长度分布）
            await cursor.execute('''
                SELECT 
                    CASE 
                        WHEN LENGTH(message) < 10 THEN '简短表达'
                        WHEN LENGTH(message) < 30 THEN '适中表达'
                        WHEN LENGTH(message) < 100 THEN '详细表达'
                        ELSE '长篇表达'
                    END as style_type,
                    COUNT(*) as count
                FROM raw_messages
                WHERE message IS NOT NULL AND LENGTH(TRIM(message)) > 0
                GROUP BY style_type
            ''')
            
            language_patterns = []
            for row in await cursor.fetchall():
                language_patterns.append({
                    'style': row[0], # 改为style字段以匹配前端
                    'type': row[0], # 保留type用于兼容性
                    'count': row[1],
                    'frequency': row[1], # 添加frequency字段用于前端显示
                    'context': 'general',
                    'environment': 'general'
                })
            
            # 如果没有语言模式数据
            if not language_patterns:
                language_patterns = [{
                    'style': '暂无语言风格数据',
                    'type': '暂无语言风格数据',
                    'count': 0,
                    'frequency': 0,
                    'context': 'general',
                    'environment': 'general'
                }]
            
            # 话题偏好分析（基于群组活跃度和智能主题识别）
            topic_preferences = []

            # 获取各个群组的消息数据进行主题分析
            await cursor.execute('''
                SELECT
                    group_id,
                    COUNT(*) as message_count,
                    AVG(LENGTH(message)) as avg_length
                FROM raw_messages
                WHERE group_id IS NOT NULL AND LENGTH(TRIM(message)) > 3
                GROUP BY group_id
                HAVING COUNT(*) > 10
                ORDER BY message_count DESC
                LIMIT 8
            ''')

            group_data = await cursor.fetchall()

            # 先收集所有group_data，避免嵌套查询
            for row in group_data:
                try:
                    # 添加行数据验证
                    if len(row) < 3:
                        self._logger.warning(f"群组话题数据行不完整 (期望3个字段，实际{len(row)}个)，跳过: {row}")
                        continue

                    group_id = row[0]
                    message_count = int(row[1]) if row[1] else 0
                    avg_length = float(row[2]) if row[2] else 0

                    # 创建新的cursor来执行嵌套查询（避免cursor状态冲突）
                    async with self.get_db_connection() as nested_conn:
                        nested_cursor = await nested_conn.cursor()

                        # 获取该群组的代表性消息进行主题分析
                        await nested_cursor.execute('''
                            SELECT message
                            FROM raw_messages
                            WHERE group_id = ? AND LENGTH(TRIM(message)) > 5 AND LENGTH(TRIM(message)) < 200
                            ORDER BY LENGTH(message) DESC, timestamp DESC
                            LIMIT 20
                        ''', (group_id,))

                        messages = await nested_cursor.fetchall()
                        await nested_cursor.close()

                        if not messages:
                            continue

                        # 智能主题识别
                        topic_analysis = self._analyze_topic_from_messages([msg[0] for msg in messages])
                        topic_name = topic_analysis['topic']
                        conversation_style = topic_analysis['style']

                        # 根据消息长度和数量推断兴趣度
                        interest_level = min(100, max(10, (message_count * avg_length) / 50))

                        topic_preferences.append({
                            'topic': topic_name,
                            'style': conversation_style,
                            'interest_level': round(interest_level, 1)
                        })
                except Exception as row_error:
                    self._logger.warning(f"处理群组话题数据行时出错，跳过: {row_error}, row: {row if 'row' in locals() and len(str(row)) < 100 else 'row too long'}")
                    continue

            # 去重：确保每个话题只出现一次，保留兴趣度最高的
            seen_topics = {}
            for pref in topic_preferences:
                try:
                    topic = pref['topic']
                    # 确保 interest_level 是数字类型
                    current_interest = float(pref.get('interest_level', 0))
                    pref['interest_level'] = current_interest

                    if topic not in seen_topics:
                        seen_topics[topic] = pref
                    else:
                        existing_interest = float(seen_topics[topic].get('interest_level', 0))
                        if current_interest > existing_interest:
                            seen_topics[topic] = pref
                except (ValueError, TypeError, KeyError) as e:
                    self._logger.warning(f"处理话题偏好时出错，跳过: {e}, pref: {pref}")

            topic_preferences = list(seen_topics.values())

            # 如果没有话题偏好数据
            if not topic_preferences:
                topic_preferences = [{
                    'topic': '暂无话题数据',
                    'style': '等待中',
                    'interest_level': 0.0
                }]
            
            return {
                'emotion_patterns': emotion_patterns,
                'language_patterns': language_patterns,
                'topic_preferences': topic_preferences
            }
            
        except Exception as e:
            self._logger.error(f"获取学习模式数据失败: {e}")
            return {
                'emotion_patterns': [
                    {'pattern': '数据获取失败，请检查系统状态', 'confidence': 0, 'frequency': 0}
                ],
                'language_patterns': [
                    {'type': '数据获取失败', 'count': 0, 'environment': 'general'}
                ],
                'topic_preferences': [
                    {'topic': '数据获取失败', 'style': 'normal', 'interest_level': 0}
                ]
            }
        finally:
            if 'cursor' in locals():
                await cursor.close()

    async def get_expression_patterns_for_webui(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取表达模式数据用于WebUI显示"""
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 检查表是否存在
                await cursor.execute('''
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='expression_patterns'
                ''')

                table_exists = await cursor.fetchone()
                if not table_exists:
                    self._logger.debug("expression_patterns表不存在")
                    return []

                # 获取表达模式数据
                await cursor.execute('''
                    SELECT situation, expression, weight, last_active_time, group_id
                    FROM expression_patterns
                    ORDER BY weight DESC, last_active_time DESC
                    LIMIT ?
                ''', (limit,))

                patterns = []
                for row in await cursor.fetchall():
                    try:
                        # 添加行数据验证
                        if len(row) < 5:
                            self._logger.warning(f"表达模式行数据不完整 (期望5个字段，实际{len(row)}个)，跳过: {row}")
                            continue

                        patterns.append({
                            'situation': row[0],
                            'expression': row[1],
                            'weight': float(row[2]) if row[2] else 0.0,
                            'last_active_time': row[3],
                            'group_id': row[4]
                        })
                    except Exception as row_error:
                        self._logger.warning(f"处理表达模式行时出错，跳过: {row_error}, row: {row}")
                        continue

                return patterns

            except Exception as e:
                self._logger.error(f"获取表达模式失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def create_style_learning_review(self, review_data: Dict[str, Any]) -> int:
        """创建对话风格学习审查记录"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 确保审查表存在
                await self._ensure_style_review_table_exists(cursor)

                # 插入审查记录
                await cursor.execute('''
                    INSERT INTO style_learning_reviews
                    (type, group_id, timestamp, learned_patterns, few_shots_content, status, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    review_data['type'],
                    review_data['group_id'],
                    review_data['timestamp'],
                    json.dumps(review_data['learned_patterns'], ensure_ascii=False),
                    review_data['few_shots_content'],
                    review_data['status'],
                    review_data['description']
                ))

                review_id = cursor.lastrowid
                await conn.commit()

                self._logger.info(f"创建风格学习审查记录成功，ID: {review_id}")
                return review_id

        except Exception as e:
            self._logger.error(f"创建风格学习审查记录失败: {e}")
            raise DataStorageError(f"创建风格学习审查记录失败: {str(e)}")

    async def _ensure_style_review_table_exists(self, cursor):
        """确保风格学习审查表存在"""
        # 根据数据库类型选择不同的 DDL
        if self.config.db_type.lower() == 'mysql':
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS style_learning_reviews (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    type VARCHAR(100) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    learned_patterns TEXT,
                    few_shots_content TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    description TEXT,
                    reviewer_comment TEXT,
                    review_time DOUBLE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_status (status),
                    INDEX idx_group (group_id),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')

            # 数据库迁移：添加缺失的字段（如果表已存在但缺少这些字段）
            try:
                # 检查并添加 reviewer_comment 字段
                await cursor.execute('''
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'style_learning_reviews'
                    AND COLUMN_NAME = 'reviewer_comment'
                ''')
                if (await cursor.fetchone())[0] == 0:
                    await cursor.execute('ALTER TABLE style_learning_reviews ADD COLUMN reviewer_comment TEXT')
                    self._logger.info(" 迁移：已添加 reviewer_comment 字段到 style_learning_reviews 表")

                # 检查并添加 review_time 字段
                await cursor.execute('''
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'style_learning_reviews'
                    AND COLUMN_NAME = 'review_time'
                ''')
                if (await cursor.fetchone())[0] == 0:
                    await cursor.execute('ALTER TABLE style_learning_reviews ADD COLUMN review_time DOUBLE')
                    self._logger.info(" 迁移：已添加 review_time 字段到 style_learning_reviews 表")
            except Exception as migration_error:
                self._logger.warning(f"数据库迁移检查失败（可能是非 MySQL 数据库）: {migration_error}")
        else:
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS style_learning_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    learned_patterns TEXT,
                    few_shots_content TEXT,
                    status TEXT DEFAULT 'pending',
                    description TEXT,
                    reviewer_comment TEXT,
                    review_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # SQLite 数据库迁移：添加缺失的字段
            try:
                # 检查表结构
                await cursor.execute("PRAGMA table_info(style_learning_reviews)")
                columns = {row[1] for row in await cursor.fetchall()}

                # 添加 reviewer_comment 字段（如果不存在）
                if 'reviewer_comment' not in columns:
                    await cursor.execute('ALTER TABLE style_learning_reviews ADD COLUMN reviewer_comment TEXT')
                    self._logger.info(" 迁移：已添加 reviewer_comment 字段到 style_learning_reviews 表 (SQLite)")

                # 添加 review_time 字段（如果不存在）
                if 'review_time' not in columns:
                    await cursor.execute('ALTER TABLE style_learning_reviews ADD COLUMN review_time REAL')
                    self._logger.info(" 迁移：已添加 review_time 字段到 style_learning_reviews 表 (SQLite)")
            except Exception as migration_error:
                self._logger.warning(f"SQLite 数据库迁移失败: {migration_error}")

    # 注意：get_pending_style_reviews 方法已在上面定义（约1456行），这里删除重复定义
    # 第一个版本是正确的，第二个版本有async with缩进bug

    async def get_pending_persona_learning_reviews(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取待审查的人格学习记录（质量不达标的学习结果）"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_pending_persona_learning_reviews_orm(limit)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 确保表存在（根据数据库类型使用不同的DDL）
                if self.config.db_type.lower() == 'mysql':
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS persona_update_reviews (
                            id INT PRIMARY KEY AUTO_INCREMENT,
                            timestamp DOUBLE NOT NULL,
                            group_id VARCHAR(255) NOT NULL,
                            update_type VARCHAR(100) NOT NULL,
                            original_content TEXT,
                            new_content TEXT,
                            proposed_content TEXT,
                            confidence_score DOUBLE,
                            reason TEXT,
                            status VARCHAR(50) NOT NULL DEFAULT 'pending',
                            reviewer_comment TEXT,
                            review_time DOUBLE,
                            INDEX idx_status (status),
                            INDEX idx_group_id (group_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')
                else:
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS persona_update_reviews (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp REAL NOT NULL,
                            group_id TEXT NOT NULL,
                            update_type TEXT NOT NULL,
                            original_content TEXT,
                            new_content TEXT,
                            proposed_content TEXT, -- 建议的新内容（兼容字段）
                            confidence_score REAL, -- 置信度得分
                            reason TEXT,
                            status TEXT NOT NULL DEFAULT 'pending',
                            reviewer_comment TEXT,
                            review_time REAL
                        )
                    ''')

                # 尝试添加metadata列（如果表已存在但没有此列）
                try:
                    await cursor.execute('ALTER TABLE persona_update_reviews ADD COLUMN metadata TEXT')
                except Exception:
                    pass # 列已存在

                await cursor.execute('''
                    SELECT id, timestamp, group_id, update_type, original_content,
                           new_content, proposed_content, confidence_score, reason, status,
                           reviewer_comment, review_time, metadata
                    FROM persona_update_reviews
                    WHERE status = 'pending'
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))

                reviews = []
                import json
                for row in await cursor.fetchall():
                    # 确保有proposed_content字段，如果为空则使用new_content
                    proposed_content = row[6] if row[6] else row[5] # proposed_content或new_content
                    confidence_score = row[7] if row[7] is not None else 0.5 # 使用数据库中的置信度

                    # 解析metadata JSON
                    metadata = {}
                    if row[12]: # metadata字段
                        try:
                            metadata = json.loads(row[12])
                        except Exception:
                            metadata = {}

                    reviews.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'group_id': row[2],
                        'update_type': row[3],
                        'original_content': row[4],
                        'new_content': row[5],
                        'proposed_content': proposed_content,
                        'confidence_score': confidence_score,
                        'reason': row[8],
                        'status': row[9],
                        'reviewer_comment': row[10],
                        'review_time': row[11],
                        'metadata': metadata # 添加metadata字段
                    })

                return reviews

        except Exception as e:
            self._logger.error(f"获取待审查人格学习记录失败: {e}")
            return []

    async def update_persona_learning_review_status(self, review_id: int, status: str, comment: str = None, modified_content: str = None) -> bool:
        """更新人格学习审查状态（使用 ORM，支持跨事件循环）"""
        try:
            if not self.db_engine:
                self._logger.warning("DatabaseEngine 未初始化，无法更新人格学习审查状态")
                return False

            from ...models.orm.learning import PersonaLearningReview

            async with self.db_engine.get_session() as session:
                review = await session.get(PersonaLearningReview, review_id)
                if not review:
                    self._logger.warning(f"未找到人格学习审查记录，ID: {review_id}")
                    return False

                review.status = status
                review.reviewer_comment = comment
                review.review_time = time.time()

                if modified_content:
                    review.proposed_content = modified_content
                    review.new_content = modified_content

                await session.commit()
                self._logger.info(f"人格学习审查状态已更新，ID: {review_id}, 状态: {status}")
                return True

        except Exception as e:
            self._logger.error(f"更新人格学习审查状态失败: {e}")
            return False

    async def delete_persona_learning_review_by_id(self, review_id: int) -> bool:
        """删除指定ID的人格学习审查记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.delete_persona_learning_review_by_id_orm(review_id)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 根据数据库类型使用不同的占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                # 删除审查记录
                await cursor.execute(f'''
                    DELETE FROM persona_update_reviews WHERE id = {placeholder}
                ''', (review_id,))

                await conn.commit()
                deleted_count = cursor.rowcount

                if deleted_count > 0:
                    self._logger.info(f"成功删除人格学习审查记录，ID: {review_id}")
                    return True
                else:
                    self._logger.warning(f"未找到要删除的人格学习审查记录，ID: {review_id}")
                    return False

        except Exception as e:
            self._logger.error(f"删除人格学习审查记录失败: {e}")
            return False

    async def delete_all_persona_learning_reviews(self, group_id: Optional[str] = None) -> int:
        """
        批量删除人格学习审查记录

        Args:
            group_id: 群组ID（可选），如果指定则只删除该群组的记录，否则删除所有记录

        Returns:
            int: 删除的记录数量
        """
        try:
            # 优先使用 ORM（支持跨事件循环）
            if self.db_engine:
                from ...models.orm.learning import PersonaLearningReview
                from sqlalchemy import delete as sa_delete

                async with self.db_engine.get_session() as session:
                    if group_id:
                        stmt = sa_delete(PersonaLearningReview).where(PersonaLearningReview.group_id == group_id)
                        self._logger.info(f"删除群组 {group_id} 的所有人格学习审查记录")
                    else:
                        stmt = sa_delete(PersonaLearningReview)
                        self._logger.info("删除所有人格学习审查记录")

                    result = await session.execute(stmt)
                    await session.commit()
                    deleted_count = result.rowcount
                    self._logger.info(f"成功删除 {deleted_count} 条人格学习审查记录")
                    return deleted_count

            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 根据数据库类型使用不同的占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                if group_id:
                    # 删除指定群组的审查记录
                    await cursor.execute(f'''
                        DELETE FROM persona_update_reviews WHERE group_id = {placeholder}
                    ''', (group_id,))
                    self._logger.info(f"删除群组 {group_id} 的所有人格学习审查记录")
                else:
                    # 删除所有审查记录
                    await cursor.execute('''
                        DELETE FROM persona_update_reviews
                    ''')
                    self._logger.info("删除所有人格学习审查记录")

                await conn.commit()
                deleted_count = cursor.rowcount

                self._logger.info(f" 成功删除 {deleted_count} 条人格学习审查记录")
                return deleted_count

        except Exception as e:
            self._logger.error(f"批量删除人格学习审查记录失败: {e}")
            return 0
    
    async def get_persona_learning_review_by_id(self, review_id: int) -> Optional[Dict[str, Any]]:
        """获取指定ID的人格学习审查记录详情"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_persona_learning_review_by_id_orm(review_id)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            await cursor.execute('''
                SELECT id, group_id, original_content, new_content, proposed_content, 
                       confidence_score, reason, status, reviewer_comment, review_time, timestamp
                FROM persona_update_reviews
                WHERE id = ?
            ''', (review_id,))
            
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'group_id': row[1],
                    'original_content': row[2],
                    'new_content': row[3],
                    'proposed_content': row[4] if row[4] else row[3], # proposed_content或new_content
                    'confidence_score': row[5] if row[5] is not None else 0.5,
                    'reason': row[6],
                    'status': row[7],
                    'reviewer_comment': row[8],
                    'review_time': row[9],
                    'timestamp': row[10]
                }
            return None
            
        except Exception as e:
            self._logger.error(f"获取人格学习审查记录失败: {e}")
            return None

    async def save_style_learning_record(self, record_data: Dict[str, Any]) -> bool:
        """保存风格学习记录到数据库"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            await cursor.execute('''
                INSERT INTO style_learning_records 
                (style_type, learned_patterns, confidence_score, sample_count, group_id, learning_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                record_data.get('style_type'),
                record_data.get('learned_patterns'),
                record_data.get('confidence_score'),
                record_data.get('sample_count'),
                record_data.get('group_id'),
                record_data.get('learning_time')
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存风格学习记录失败: {e}")
            return False

    async def save_language_style_pattern(self, pattern_data: Dict[str, Any]) -> bool:
        """保存语言风格模式到数据库"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # 先检查是否已存在相同的语言风格
            await cursor.execute('''
                SELECT id FROM language_style_patterns 
                WHERE language_style = ? AND group_id = ?
            ''', (pattern_data.get('language_style'), pattern_data.get('group_id')))
            
            existing = await cursor.fetchone()
            
            if existing:
                # 更新现有记录
                await cursor.execute('''
                    UPDATE language_style_patterns 
                    SET example_phrases = ?, usage_frequency = ?, context_type = ?, last_updated = ?
                    WHERE id = ?
                ''', (
                    pattern_data.get('example_phrases'),
                    pattern_data.get('usage_frequency'),
                    pattern_data.get('context_type'),
                    pattern_data.get('last_updated'),
                    existing[0]
                ))
            else:
                # 插入新记录
                await cursor.execute('''
                    INSERT INTO language_style_patterns 
                    (language_style, example_phrases, usage_frequency, context_type, group_id, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    pattern_data.get('language_style'),
                    pattern_data.get('example_phrases'),
                    pattern_data.get('usage_frequency'),
                    pattern_data.get('context_type'),
                    pattern_data.get('group_id'),
                    pattern_data.get('last_updated')
                ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存语言风格模式失败: {e}")
            return False

    async def get_reviewed_persona_learning_updates(self, limit: int = 50, offset: int = 0, status_filter: str = None) -> List[Dict[str, Any]]:
        """获取已审查的人格学习更新记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_reviewed_persona_learning_updates_orm(limit, offset, status_filter)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # 构建查询条件
            where_clause = "WHERE status != 'pending'"
            params = []
            
            if status_filter:
                where_clause += " AND status = ?"
                params.append(status_filter)
            
            # 首先检查表是否存在并获取表结构
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='persona_update_reviews'")
            table_exists = await cursor.fetchone()
            
            if not table_exists:
                self._logger.info("persona_update_reviews表不存在，返回空列表")
                return []
            
            # 检查表结构，确定正确的字段名
            await cursor.execute("PRAGMA table_info(persona_update_reviews)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # 根据实际的列名构建查询
            if 'proposed_content' in column_names:
                content_field = 'proposed_content'
            elif 'new_content' in column_names:
                content_field = 'new_content'
            else:
                # 如果两个字段都不存在，使用原始内容
                content_field = 'original_content'

            # 检查是否有metadata列
            has_metadata = 'metadata' in column_names

            # 使用实际存在的字段进行查询，并处理NULL值
            metadata_field = ', metadata' if has_metadata else ''
            await cursor.execute(f'''
                SELECT id, group_id, original_content, {content_field}, reason,
                       status, reviewer_comment, review_time, timestamp{metadata_field}
                FROM persona_update_reviews
                {where_clause}
                ORDER BY COALESCE(review_time, timestamp) DESC
                LIMIT ? OFFSET ?
            ''', params + [limit, offset])

            rows = await cursor.fetchall()
            updates = []

            import json
            for row in rows:
                # 解析metadata（如果存在）
                metadata = {}
                if has_metadata and len(row) > 9 and row[9]:
                    try:
                        metadata = json.loads(row[9])
                    except Exception:
                        metadata = {}

                updates.append({
                    'id': f"persona_learning_{row[0]}",
                    'group_id': row[1] or 'default',
                    'original_content': row[2] or '',
                    'proposed_content': row[3] or '', # 使用实际存在的字段
                    'reason': row[4] or '人格学习更新',
                    'confidence_score': metadata.get('confidence_score', 0.8), # 从metadata获取或使用默认值
                    'status': row[5],
                    'reviewer_comment': row[6] or '',
                    'review_time': row[7] if row[7] else 0,
                    'timestamp': row[8] if row[8] else 0,
                    'update_type': 'persona_learning_review',
                    # 添加metadata中的关键字段
                    'features_content': metadata.get('features_content', ''),
                    'llm_response': metadata.get('llm_response', ''),
                    'total_raw_messages': metadata.get('total_raw_messages', 0),
                    'messages_analyzed': metadata.get('messages_analyzed', 0),
                    'metadata': metadata
                })
            
            return updates
            
        except Exception as e:
            self._logger.error(f"获取已审查人格学习记录失败: {e}")
            # 如果是表或列不存在的错误，返回空列表
            if "no such table" in str(e).lower() or "no such column" in str(e).lower():
                self._logger.info("人格学习审查表或字段不存在，返回空列表")
                return []
            return []

    async def get_reviewed_style_learning_updates(self, limit: int = 50, offset: int = 0, status_filter: str = None) -> List[Dict[str, Any]]:
        """获取已审查的风格学习更新记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.get_reviewed_style_learning_updates_orm(limit, offset, status_filter)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # 构建查询条件
            where_clause = "WHERE status != 'pending'"
            params = []
            
            if status_filter:
                where_clause += " AND status = ?"
                params.append(status_filter)
            
            # 使用正确的字段名，没有review_time字段，使用updated_at，并处理NULL值
            await cursor.execute(f'''
                SELECT id, type, group_id, timestamp, learned_patterns, status, updated_at, description
                FROM style_learning_reviews
                {where_clause}
                ORDER BY COALESCE(updated_at, timestamp) DESC
                LIMIT ? OFFSET ?
            ''', params + [limit, offset])
            
            rows = await cursor.fetchall()
            updates = []
            
            for row in rows:
                # 添加行数据验证
                try:
                    if len(row) < 8:
                        self._logger.warning(f"风格学习记录行数据不完整，跳过: {row}")
                        continue

                    # 尝试解析learned_patterns以获取更多信息
                    try:
                        learned_patterns = json.loads(row[4]) if row[4] else {}
                        reason = learned_patterns.get('reason', '风格学习更新')
                        original_content = learned_patterns.get('original_content', '原始风格特征')
                        proposed_content = learned_patterns.get('proposed_content', row[4]) # 使用完整的learned_patterns作为proposed_content
                        confidence_score = learned_patterns.get('confidence_score', 0.8)
                    except (json.JSONDecodeError, AttributeError):
                        reason = row[7] if len(row) > 7 and row[7] else '风格学习更新' # 使用description字段
                        original_content = '原始风格特征'
                        proposed_content = row[4] if len(row) > 4 and row[4] else '无内容'
                        confidence_score = 0.8

                    updates.append({
                        'id': row[0],
                        'group_id': row[2],
                        'original_content': original_content,
                        'proposed_content': proposed_content,
                        'reason': reason,
                        'confidence_score': confidence_score,
                        'status': row[5],
                        'reviewer_comment': '', # 风格审查没有备注字段
                        'review_time': row[6] if len(row) > 6 else None, # 使用updated_at字段
                        'timestamp': row[3],
                        'update_type': f'style_learning_{row[1]}'
                    })
                except Exception as row_error:
                    self._logger.warning(f"处理风格学习记录行时出错，跳过: {row_error}, row: {row if len(row) < 20 else 'too long'}")
            
            return updates
            
        except Exception as e:
            self._logger.error(f"获取已审查风格学习记录失败: {e}")
            # 如果表不存在，返回空列表
            if "no such table" in str(e).lower():
                self._logger.info("风格学习审查表不存在，返回空列表")
                return []
            return []

    async def get_reviewed_persona_update_records(self, limit: int = 50, offset: int = 0, status_filter: str = None) -> List[Dict[str, Any]]:
        """获取已审查的传统人格更新记录"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

            # 构建查询条件
            where_clause = "WHERE status != 'pending'"
            params = []

            if status_filter:
                where_clause += " AND status = ?"
                params.append(status_filter)

            query = f'''
                SELECT id, timestamp, group_id, update_type, original_content, new_content,
                       reason, status, reviewer_comment, review_time
                FROM persona_update_records
                {where_clause}
                ORDER BY COALESCE(review_time, timestamp) DESC
                LIMIT ? OFFSET ?
            '''

            self._logger.debug(f"执行人格更新记录查询: params={params + [limit, offset]}")
            await cursor.execute(query, params + [limit, offset])
            
            rows = await cursor.fetchall()
            records = []

            for row in rows:
                # 添加行数据验证
                try:
                    if len(row) < 10:
                        self._logger.warning(f"人格更新记录行数据不完整 (期望10个字段，实际{len(row)}个)，跳过: {row}")
                        continue

                    records.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'group_id': row[2],
                        'update_type': row[3],
                        'original_content': row[4],
                        'new_content': row[5],
                        'reason': row[6],
                        'status': row[7],
                        'reviewer_comment': row[8] if row[8] else '',
                        'review_time': row[9]
                    })
                except Exception as row_error:
                    self._logger.warning(f"处理人格更新记录行时出错，跳过: {row_error}, row: {row if len(row) < 20 else 'too long'}")
            
            return records
            
        except Exception as e:
            self._logger.error(f"获取已审查传统人格更新记录失败: {e}")
            return []

    async def update_style_review_status(self, review_id: int, status: str, group_id: str = None) -> bool:
        """更新风格学习审查状态"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.update_style_review_status_orm(review_id, status, group_id)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    UPDATE style_learning_reviews
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                ''', (status, time.time(), review_id))

                await conn.commit()

                if cursor.rowcount > 0:
                    self._logger.info(f"更新风格学习审查状态成功: ID={review_id}, 状态={status}")
                    return True
                else:
                    self._logger.warning(f"更新风格学习审查状态失败: 未找到ID={review_id}的记录")
                    return False

        except Exception as e:
            self._logger.error(f"更新风格学习审查状态失败: {e}")
            return False

    async def delete_style_review_by_id(self, review_id: int) -> bool:
        """删除指定ID的风格学习审查记录"""
        # 优先使用 ORM（支持跨事件循环）
        if self.db_engine:
            return await self.delete_style_review_by_id_orm(review_id)
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 删除审查记录
                await cursor.execute('''
                    DELETE FROM style_learning_reviews WHERE id = ?
                ''', (review_id,))

                await conn.commit()
                deleted_count = cursor.rowcount

                await cursor.close()

                if deleted_count > 0:
                    self._logger.info(f"成功删除风格学习审查记录，ID: {review_id}")
                    return True
                else:
                    self._logger.warning(f"未找到要删除的风格学习审查记录，ID: {review_id}")
                    return False

        except Exception as e:
            self._logger.error(f"删除风格学习审查记录失败: {e}")
            return False

    async def get_detailed_metrics(self) -> Dict[str, Any]:
        """获取详细性能监控数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # API指标（基于学习批次的执行时间）
            # 修复：使用数据库无关的时间格式化方式
            if self.config.db_type == 'sqlite': # 修正：self.db_type → self.config.db_type
                # SQLite语法
                await cursor.execute('''
                    SELECT
                        strftime('%H', datetime(start_time, 'unixepoch')) as hour,
                        AVG((CASE WHEN end_time IS NOT NULL THEN end_time - start_time ELSE 0 END)) as avg_response_time
                    FROM learning_batches
                    WHERE start_time > ? AND end_time IS NOT NULL
                    GROUP BY hour
                    ORDER BY hour
                ''', (time.time() - 86400,))
            else:
                # MySQL语法
                await cursor.execute('''
                    SELECT
                        HOUR(FROM_UNIXTIME(start_time)) as hour,
                        AVG((CASE WHEN end_time IS NOT NULL THEN end_time - start_time ELSE 0 END)) as avg_response_time
                    FROM learning_batches
                    WHERE start_time > %s AND end_time IS NOT NULL
                    GROUP BY hour
                    ORDER BY hour
                ''', (time.time() - 86400,))
            
            api_hours = []
            api_response_times = []
            for row in await cursor.fetchall():
                api_hours.append(f"{row[0]}:00")
                api_response_times.append(round(row[1] * 1000, 2)) # 转换为毫秒
            
            # 数据库表统计
            tables_to_check = ['raw_messages', 'filtered_messages', 'learning_batches', 'persona_update_records']
            table_stats = {}
            
            for table in tables_to_check:
                try:
                    await cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    count = await cursor.fetchone()
                    table_stats[table] = count[0] if count else 0
                except Exception as table_error:
                    self._logger.debug(f"无法获取表 {table} 统计: {table_error}")
                    table_stats[table] = 0
            
            # 系统指标
            import psutil
            try:
                memory = psutil.virtual_memory()
                # 在Windows上使用主驱动器
                disk_path = 'C:\\' if os.name == 'nt' else '/'
                disk = psutil.disk_usage(disk_path)
                
                system_metrics = {
                    'memory_percent': memory.percent,
                    'cpu_percent': psutil.cpu_percent(),
                    'disk_percent': round(disk.used / disk.total * 100, 2)
                }
            except Exception as system_error:
                self._logger.warning(f"获取系统指标失败: {system_error}")
                system_metrics = {
                    'memory_percent': 0,
                    'cpu_percent': 0,
                    'disk_percent': 0
                }
            
            return {
                'api_metrics': {
                    'hours': api_hours,
                    'response_times': api_response_times
                },
                'database_metrics': {
                    'table_stats': table_stats
                },
                'system_metrics': system_metrics
            }
            
        except Exception as e:
            self._logger.error(f"获取详细监控数据失败: {e}")
            return {
                'api_metrics': {
                    'hours': [],
                    'response_times': []
                },
                'database_metrics': {
                    'table_stats': {}
                },
                'system_metrics': {
                    'memory_percent': 0,
                    'cpu_percent': 0,
                    'disk_percent': 0
                }
            }

    async def get_trends_data(self) -> Dict[str, Any]:
        """获取指标趋势数据"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            # 计算7天和30天前的时间戳
            now = time.time()
            week_ago = now - (7 * 24 * 3600)
            month_ago = now - (30 * 24 * 3600)
            
            # 消息增长趋势
            await cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN timestamp > ? THEN 1 END) as week_count,
                    COUNT(CASE WHEN timestamp > ? THEN 1 END) as month_count,
                    COUNT(*) as total_count
                FROM raw_messages
            ''', (week_ago, month_ago))
            
            message_stats = await cursor.fetchone()
            if message_stats and len(message_stats) >= 3:
                week_messages = int(message_stats[0]) if message_stats[0] else 0
                month_messages = int(message_stats[1]) if message_stats[1] else 0
                total_messages = int(message_stats[2]) if message_stats[2] else 0

                # 计算增长率
                if month_messages > week_messages:
                    message_growth = ((week_messages * 4 - (month_messages - week_messages)) / (month_messages - week_messages) * 100) if (month_messages - week_messages) > 0 else 0
                else:
                    message_growth = 0
            elif message_stats:
                self._logger.warning(f"消息统计数据行不完整 (期望3个字段，实际{len(message_stats)}个): {message_stats}")
                message_growth = 0
                week_messages = 0
                month_messages = 0
                total_messages = 0
            else:
                message_growth = 0
                week_messages = 0
                month_messages = 0
                total_messages = 0
            
            # 筛选消息增长趋势
            await cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN timestamp > ? THEN 1 END) as week_filtered,
                    COUNT(CASE WHEN timestamp > ? THEN 1 END) as month_filtered
                FROM filtered_messages
            ''', (week_ago, month_ago))
            
            filtered_stats = await cursor.fetchone()
            if filtered_stats and len(filtered_stats) >= 2:
                week_filtered = int(filtered_stats[0]) if filtered_stats[0] else 0
                month_filtered = int(filtered_stats[1]) if filtered_stats[1] else 0

                # 计算增长率
                if month_filtered > week_filtered:
                    filtered_growth = ((week_filtered * 4 - (month_filtered - week_filtered)) / (month_filtered - week_filtered) * 100) if (month_filtered - week_filtered) > 0 else 0
                else:
                    filtered_growth = 0
            elif filtered_stats:
                self._logger.warning(f"筛选消息统计数据行不完整 (期望2个字段，实际{len(filtered_stats)}个): {filtered_stats}")
                week_filtered = 0
                month_filtered = 0
                filtered_growth = 0
            else:
                week_filtered = 0
                month_filtered = 0
                filtered_growth = 0
            
            # LLM调用增长（基于学习批次）
            await cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN start_time > ? THEN 1 END) as week_sessions,
                    COUNT(CASE WHEN start_time > ? THEN 1 END) as month_sessions
                FROM learning_batches
            ''', (week_ago, month_ago))
            
            session_stats = await cursor.fetchone()
            if session_stats and len(session_stats) >= 2:
                week_sessions = int(session_stats[0]) if session_stats[0] else 0
                month_sessions = int(session_stats[1]) if session_stats[1] else 0

                # 计算增长率
                if month_sessions > week_sessions:
                    sessions_growth = ((week_sessions * 4 - (month_sessions - week_sessions)) / (month_sessions - week_sessions) * 100) if (month_sessions - week_sessions) > 0 else 0
                else:
                    sessions_growth = 0
            elif session_stats:
                self._logger.warning(f"学习批次统计数据行不完整 (期望2个字段，实际{len(session_stats)}个): {session_stats}")
                week_sessions = 0
                month_sessions = 0
                sessions_growth = 0
            else:
                week_sessions = 0
                month_sessions = 0
                sessions_growth = 0
            
            return {
                'message_growth': round(message_growth, 1),
                'filtered_growth': round(filtered_growth, 1),
                'llm_growth': round(sessions_growth, 1),
                'sessions_growth': round(sessions_growth, 1)
            }
            
        except Exception as e:
            self._logger.error(f"获取趋势数据失败: {e}")
            return {
                'message_growth': 0,
                'filtered_growth': 0,
                'llm_growth': 0,
                'sessions_growth': 0
            }

    def _analyze_topic_from_messages(self, messages: List[str]) -> Dict[str, str]:
        """
        基于消息内容智能分析群聊主题
        
        Args:
            messages: 消息列表
            
        Returns:
            包含topic和style的字典
        """
        try:
            if not messages:
                return {'topic': '空群聊', 'style': 'unknown'}
            
            # 合并所有消息文本
            all_text = ' '.join(messages).lower()
            
            # 定义主题关键词库
            topic_keywords = {
                '技术讨论': ['代码', '编程', 'python', 'java', 'javascript', 'bug', '算法', '开发', '前端', '后端', 'api', '数据库', 'sql', 'git', '项目', '需求', '测试', '部署'],
                '游戏娱乐': ['游戏', '玩家', '攻略', '装备', '副本', '公会', 'pvp', '角色', '技能', '等级', '经验', '任务', '活动', '充值', '抽卡', '开黑', '上分'],
                '学习交流': ['学习', '作业', '考试', '复习', '笔记', '课程', '老师', '同学', '知识', '问题', '答案', '教程', '资料', '书籍', '论文', '研究'],
                '工作协作': ['工作', '会议', '项目', '任务', '进度', '汇报', '客户', '合作', '团队', '领导', '同事', '业务', '方案', '文档', '流程', '审批'],
                '生活日常': ['吃饭', '睡觉', '天气', '心情', '家人', '朋友', '购物', '电影', '音乐', '旅游', '美食', '健康', '运动', '休息', '周末'],
                '兴趣爱好': ['摄影', '绘画', '音乐', '电影', '书籍', '旅行', '美食', '运动', '健身', '瑜伽', '跑步', '骑行', '爬山', '游泳', '篮球'],
                '商务合作': ['合作', '商务', '业务', '客户', '项目', '方案', '报价', '合同', '付款', '发票', '产品', '服务', '市场', '销售', '推广'],
                '技术支持': ['问题', '故障', '错误', '修复', '解决', '帮助', '支持', '教程', '指导', '操作', '配置', '安装', '更新', '维护', '优化'],
                '闲聊灌水': ['哈哈', '嘿嘿', '', '', '笑死', '有趣', '无聊', '随便', '聊天', '扯淡', '吐槽', '搞笑', '段子', '表情', '发呆'],
                '通知公告': ['通知', '公告', '重要', '注意', '提醒', '截止', '时间', '安排', '活动', '报名', '参加', '会议', '培训', '讲座', '活动']
            }
            
            # 分析主题匹配度
            topic_scores = {}
            for topic, keywords in topic_keywords.items():
                score = 0
                for keyword in keywords:
                    score += all_text.count(keyword)
                topic_scores[topic] = score
            
            # 获取得分最高的主题
            best_topic = max(topic_scores.items(), key=lambda x: x[1])
            
            if best_topic[1] == 0: # 没有匹配到任何关键词
                return {'topic': '综合聊天', 'style': '日常对话'}
            
            # 根据主题确定对话风格
            style_mapping = {
                '技术讨论': '技术交流',
                '游戏娱乐': '轻松娱乐', 
                '学习交流': '学术讨论',
                '工作协作': '工作协调',
                '生活日常': '日常闲聊',
                '兴趣爱好': '兴趣分享',
                '商务合作': '商务沟通',
                '技术支持': '技术答疑',
                '闲聊灌水': '轻松聊天',
                '通知公告': '信息通知'
            }
            
            topic = best_topic[0]
            style = style_mapping.get(topic, '日常对话')
            
            return {
                'topic': topic,
                'style': style
            }
            
        except Exception as e:
            self._logger.error(f"主题分析失败: {e}")
            return {'topic': '未知主题', 'style': '日常对话'}

    async def get_recent_learning_batches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的学习批次记录"""
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()
            
            await cursor.execute('''
                SELECT id, group_id, start_time, end_time, quality_score,
                       processed_messages, batch_name, message_count, 
                       filtered_count, success, error_message
                FROM learning_batches 
                ORDER BY start_time DESC 
                LIMIT ?
            ''', (limit,))
            
            batches = []
            for row in await cursor.fetchall():
                try:
                    # 添加行数据验证
                    if len(row) < 11:
                        self._logger.warning(f"学习批次记录行数据不完整 (期望11个字段，实际{len(row)}个)，跳过: {row}")
                        continue

                    batches.append({
                        'id': int(row[0]) if row[0] else 0,
                        'group_id': row[1],
                        'start_time': float(row[2]) if row[2] else 0,
                        'end_time': float(row[3]) if row[3] else 0,
                        'quality_score': float(row[4]) if row[4] else 0,
                        'processed_messages': int(row[5]) if row[5] else 0,
                        'batch_name': row[6],
                        'message_count': int(row[7]) if row[7] else 0,
                        'filtered_count': int(row[8]) if row[8] else 0,
                        'success': bool(row[9]) if row[9] is not None else False,
                        'error_message': row[10]
                    })
                except Exception as row_error:
                    self._logger.warning(f"处理学习批次记录行时出错，跳过: {row_error}, row: {row if len(str(row)) < 100 else 'row too long'}")
                    continue
            
            return batches

        except Exception as e:
            self._logger.error(f"获取学习批次记录失败: {e}")
            return []

    async def add_persona_learning_review(
        self,
        group_id: str,
        proposed_content: str,
        learning_source: str = UPDATE_TYPE_EXPRESSION_LEARNING, # 使用常量作为默认值
        confidence_score: float = 0.5,
        raw_analysis: str = "",
        metadata: Dict[str, Any] = None,
        original_content: str = "", # 新增：原人格完整文本
        new_content: str = "" # 新增：新人格完整文本（原人格+增量）
    ) -> int:
        """添加人格学习审查记录

        Args:
            group_id: 群组ID
            proposed_content: 建议的增量人格内容
            learning_source: 学习来源
            confidence_score: 置信度分数
            raw_analysis: 原始分析结果
            metadata: 元数据(包含features_content, llm_response, sample counts等)
            original_content: 原人格完整文本（用于前端显示对比）
            new_content: 新人格完整文本（原人格+增量，用于前端高亮显示）

        Returns:
            插入记录的ID
        """
        try:
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 确保表存在并添加metadata列
                # 根据数据库类型使用不同的DDL
                if self.config.db_type.lower() == 'mysql':
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS persona_update_reviews (
                            id INT PRIMARY KEY AUTO_INCREMENT,
                            timestamp DOUBLE NOT NULL,
                            group_id VARCHAR(255) NOT NULL,
                            update_type VARCHAR(100) NOT NULL,
                            original_content TEXT,
                            new_content TEXT,
                            proposed_content TEXT,
                            confidence_score DOUBLE,
                            reason TEXT,
                            status VARCHAR(50) NOT NULL DEFAULT 'pending',
                            reviewer_comment TEXT,
                            review_time DOUBLE,
                            metadata JSON,
                            INDEX idx_group_id (group_id),
                            INDEX idx_status (status),
                            INDEX idx_timestamp (timestamp)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    ''')
                else:
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS persona_update_reviews (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp REAL NOT NULL,
                            group_id TEXT NOT NULL,
                            update_type TEXT NOT NULL,
                            original_content TEXT,
                            new_content TEXT,
                            proposed_content TEXT,
                            confidence_score REAL,
                            reason TEXT,
                            status TEXT NOT NULL DEFAULT 'pending',
                            reviewer_comment TEXT,
                            review_time REAL,
                            metadata TEXT
                        )
                    ''')

                # 尝试添加metadata列（如果表已存在但没有此列）
                try:
                    await cursor.execute('ALTER TABLE persona_update_reviews ADD COLUMN metadata TEXT')
                except Exception:
                    pass # 列已存在

                # 准备元数据JSON
                import json
                metadata_json = json.dumps(metadata if metadata else {}, ensure_ascii=False)

                # 修复：使用传入的 original_content 和 new_content
                # 如果 new_content 为空，则使用 proposed_content（向后兼容）
                final_new_content = new_content if new_content else proposed_content

                # 根据数据库类型使用不同的占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                # 插入记录
                placeholders = ', '.join([placeholder] * 10)
                await cursor.execute(f'''
                    INSERT INTO persona_update_reviews
                    (timestamp, group_id, update_type, original_content, new_content,
                     proposed_content, confidence_score, reason, status, metadata)
                    VALUES ({placeholders})
                ''', (
                    time.time(),
                    group_id,
                    learning_source, # update_type就是learning_source
                    original_content, # 使用传入的原人格文本
                    final_new_content, # 使用完整的新人格文本
                    proposed_content, # proposed_content保持为增量部分
                    confidence_score,
                    raw_analysis, # reason字段存储raw_analysis
                    'pending',
                    metadata_json
                ))

                await conn.commit()
                record_id = cursor.lastrowid

                self._logger.info(f"添加人格学习审查记录成功，ID: {record_id}, 群组: {group_id}")
                return record_id

        except Exception as e:
            self._logger.error(f"添加人格学习审查记录失败: {e}")
            raise

    async def get_messages_by_group_and_timerange(
        self,
        group_id: str,
        start_time: float = None,
        end_time: float = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取指定群组在指定时间范围内的聊天记录

        Args:
            group_id: 群组ID
            start_time: 开始时间戳（秒），None表示不限制
            end_time: 结束时间戳（秒），None表示不限制
            limit: 返回消息数量限制

        Returns:
            消息记录列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                query = '''
                    SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                    FROM raw_messages
                    WHERE group_id = ?
                '''
                params = [group_id]

                if start_time is not None:
                    query += ' AND timestamp >= ?'
                    params.append(start_time)

                if end_time is not None:
                    query += ' AND timestamp <= ?'
                    params.append(end_time)

                query += ' ORDER BY timestamp DESC LIMIT ?'
                params.append(limit)

                await cursor.execute(query, params)

                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2],
                        'content': row[3], # 外部API使用 'content' 字段名
                        'group_id': row[4],
                        'platform': row[5],
                        'timestamp': row[6],
                        'processed': row[7]
                    })

                self._logger.info(f" API查询结果: group={group_id}, 返回{len(messages)}条消息, 最新timestamp={messages[0]['timestamp'] if messages else 'N/A'}")
                return messages

            except aiosqlite.Error as e:
                self._logger.error(f"获取时间范围消息失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_new_messages_since(
        self,
        group_id: str,
        last_message_id: int = None,
        last_timestamp: float = None
    ) -> List[Dict[str, Any]]:
        """
        获取指定群组的增量消息（自上次获取后的新消息）

        Args:
            group_id: 群组ID
            last_message_id: 上次获取的最后一条消息ID
            last_timestamp: 上次获取的最后一条消息时间戳

        Returns:
            新消息列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 优先使用message_id，如果没有则使用timestamp
                if last_message_id is not None:
                    query = '''
                        SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                        FROM raw_messages
                        WHERE group_id = ? AND id > ?
                        ORDER BY timestamp ASC
                    '''
                    params = (group_id, last_message_id)
                elif last_timestamp is not None:
                    query = '''
                        SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                        FROM raw_messages
                        WHERE group_id = ? AND timestamp > ?
                        ORDER BY timestamp ASC
                    '''
                    params = (group_id, last_timestamp)
                else:
                    # 如果两个参数都没有，返回最近的消息
                    query = '''
                        SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                        FROM raw_messages
                        WHERE group_id = ?
                        ORDER BY timestamp DESC
                        LIMIT 20
                    '''
                    params = (group_id,)

                await cursor.execute(query, params)

                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2],
                        'content': row[3], # 外部API使用 'content' 字段名
                        'group_id': row[4],
                        'platform': row[5],
                        'timestamp': row[6],
                        'processed': row[7]
                    })

                return messages

            except aiosqlite.Error as e:
                self._logger.error(f"获取增量消息失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_current_topic_summary(self, group_id: str, recent_messages_count: int = 20) -> Dict[str, Any]:
        """
        获取指定群组当前的聊天话题总结

        优先从数据库中读取最近的话题总结,如果没有或过期(超过30分钟),则分析最近消息生成新的总结

        Args:
            group_id: 群组ID
            recent_messages_count: 分析的最近消息数量

        Returns:
            话题总结信息
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 首先尝试从数据库获取最近30分钟内的话题总结
                thirty_minutes_ago = time.time() - 1800
                await cursor.execute('''
                    SELECT topic, summary, participants, message_count,
                           start_timestamp, end_timestamp, generated_at
                    FROM topic_summaries
                    WHERE group_id = ? AND generated_at > ?
                    ORDER BY generated_at DESC
                    LIMIT 1
                ''', (group_id, thirty_minutes_ago))

                cached_summary = await cursor.fetchone()

                if cached_summary:
                    # 返回缓存的话题总结
                    import json
                    participants = json.loads(cached_summary[2]) if cached_summary[2] else []

                    return {
                        'group_id': group_id,
                        'topic': cached_summary[0],
                        'summary': cached_summary[1],
                        'participants': participants,
                        'message_count': cached_summary[3],
                        'start_timestamp': cached_summary[4],
                        'latest_timestamp': cached_summary[5],
                        'generated_at': cached_summary[6],
                        'from_cache': True
                    }

                # 如果没有缓存,获取最近的消息生成新总结
                await cursor.execute('''
                    SELECT message, sender_name, timestamp
                    FROM raw_messages
                    WHERE group_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (group_id, recent_messages_count))

                messages = []
                latest_timestamp = None
                earliest_timestamp = None
                for row in await cursor.fetchall():
                    messages.append({
                        'message': row[0],
                        'sender_name': row[1],
                        'timestamp': row[2]
                    })
                    if latest_timestamp is None or row[2] > latest_timestamp:
                        latest_timestamp = row[2]
                    if earliest_timestamp is None or row[2] < earliest_timestamp:
                        earliest_timestamp = row[2]

                if not messages:
                    return {
                        'group_id': group_id,
                        'topic': '暂无聊天记录',
                        'participants': [],
                        'message_count': 0,
                        'latest_timestamp': 0,
                        'summary': '群组暂无聊天活动',
                        'from_cache': False
                    }

                # 统计参与者
                participants = list(set([msg['sender_name'] for msg in messages]))

                # 使用已有的话题分析方法
                messages_text = [msg['message'] for msg in messages]
                topic_analysis = self._analyze_topic_from_messages(messages_text)

                topic_result = {
                    'group_id': group_id,
                    'topic': topic_analysis['topic'],
                    'summary': f"最近{len(messages)}条消息讨论了{topic_analysis['topic']},对话风格为{topic_analysis['style']}",
                    'participants': participants,
                    'message_count': len(messages),
                    'start_timestamp': earliest_timestamp,
                    'latest_timestamp': latest_timestamp,
                    'generated_at': time.time(),
                    'recent_messages': messages[:5], # 返回最近5条消息内容供参考
                    'from_cache': False
                }

                # 保存到数据库以供后续查询
                # 不等待保存完成,避免阻塞API响应
                asyncio.create_task(self._save_topic_summary(group_id, topic_result))

                return topic_result

            except aiosqlite.Error as e:
                self._logger.error(f"获取话题总结失败: {e}", exc_info=True)
                return {
                    'group_id': group_id,
                    'topic': '获取失败',
                    'participants': [],
                    'message_count': 0,
                    'latest_timestamp': 0,
                    'summary': f'获取话题失败: {str(e)}',
                    'from_cache': False
                }
            finally:
                await cursor.close()

    async def _save_topic_summary(self, group_id: str, topic_data: Dict[str, Any]):
        """
        保存话题总结到数据库

        Args:
            group_id: 群组ID
            topic_data: 话题数据
        """
        try:
            import json
            async with self.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    INSERT INTO topic_summaries
                    (group_id, topic, summary, participants, message_count,
                     start_timestamp, end_timestamp, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    group_id,
                    topic_data.get('topic', ''),
                    topic_data.get('summary', ''),
                    json.dumps(topic_data.get('participants', []), ensure_ascii=False),
                    topic_data.get('message_count', 0),
                    topic_data.get('start_timestamp'),
                    topic_data.get('latest_timestamp'),
                    topic_data.get('generated_at', time.time())
                ))

                await conn.commit()
                await cursor.close()

                self._logger.debug(f"已保存群组 {group_id} 的话题总结")

        except Exception as e:
            self._logger.error(f"保存话题总结失败: {e}", exc_info=True)

    async def get_all_expression_patterns(self, group_id: str) -> List[Dict[str, Any]]:
        """
        获取指定群组的所有表达模式

        Args:
            group_id: 群组ID

        Returns:
            表达模式列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    SELECT context, expression, quality_score, last_used_timestamp
                    FROM expression_patterns
                    WHERE group_id = ?
                    ORDER BY quality_score DESC, last_used_timestamp DESC
                ''', (group_id,))

                patterns = []
                for row in await cursor.fetchall():
                    patterns.append({
                        'context': row[0],
                        'expression': row[1],
                        'quality_score': row[2],
                        'last_used_timestamp': row[3]
                    })

                return patterns

            except aiosqlite.Error as e:
                self._logger.error(f"获取表达模式失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_all_expression_patterns_by_group(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有群组的表达模式（按群组分组）

        Returns:
            Dict[str, List[Dict[str, Any]]]: 群组ID -> 表达模式列表的映射
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    SELECT id, situation, expression, weight, last_active_time, create_time, group_id
                    FROM expression_patterns
                    ORDER BY group_id, last_active_time DESC
                ''')

                patterns_by_group = {}
                for row in await cursor.fetchall():
                    group_id = row[6]
                    if group_id not in patterns_by_group:
                        patterns_by_group[group_id] = []

                    patterns_by_group[group_id].append({
                        'id': row[0],
                        'situation': row[1],
                        'expression': row[2],
                        'weight': row[3],
                        'last_active_time': row[4],
                        'created_time': row[5],
                        'group_id': group_id,
                        'style_type': 'general'
                    })

                return patterns_by_group

            except Exception as e:
                self._logger.error(f"获取所有表达模式失败: {e}", exc_info=True)
                return {}
            finally:
                await cursor.close()

    async def get_recent_week_expression_patterns(self, group_id: str = None, limit: int = 20, hours: int = 168) -> List[Dict[str, Any]]:
        """
        获取最近指定小时内学习到的表达模式（按质量分数和时间排序）

        Args:
            group_id: 群组ID，如果为None则获取全局所有群组的表达模式
            limit: 获取数量限制
            hours: 时间范围(小时)，默认168小时(一周)

        Returns:
            表达模式列表，包含场景(situation)和表达(expression)
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 计算时间阈值
                time_threshold = time.time() - (hours * 3600)

                # 根据group_id是否为None决定查询条件
                if group_id is None:
                    # 全局查询：从所有群组获取表达模式
                    await cursor.execute('''
                        SELECT situation, expression, weight, last_active_time, create_time, group_id
                        FROM expression_patterns
                        WHERE last_active_time > ?
                        ORDER BY weight DESC, last_active_time DESC
                        LIMIT ?
                    ''', (time_threshold, limit))
                else:
                    # 单群组查询：只获取指定群组的表达模式
                    await cursor.execute('''
                        SELECT situation, expression, weight, last_active_time, create_time, group_id
                        FROM expression_patterns
                        WHERE group_id = ? AND last_active_time > ?
                        ORDER BY weight DESC, last_active_time DESC
                        LIMIT ?
                    ''', (group_id, time_threshold, limit))

                patterns = []
                for row in await cursor.fetchall():
                    patterns.append({
                        'situation': row[0], # 场景描述
                        'expression': row[1], # 表达方式
                        'weight': row[2], # 权重
                        'last_active_time': row[3], # 最后活跃时间
                        'create_time': row[4], # 创建时间
                        'group_id': row[5] if len(row) > 5 else group_id # 群组ID（全局查询时有用）
                    })

                return patterns

            except aiosqlite.Error as e:
                self._logger.error(f"获取最近一周表达模式失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_recent_bot_responses(self, group_id: str, limit: int = 10) -> List[str]:
        """
        获取Bot最近的回复内容（用于同质化分析）- 从bot_messages表读取

        Args:
            group_id: 群组ID
            limit: 获取数量

        Returns:
            回复内容列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 从bot_messages表读取Bot的回复
                await cursor.execute('''
                    SELECT message
                    FROM bot_messages
                    WHERE group_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (group_id, limit))

                responses = []
                for row in await cursor.fetchall():
                    responses.append(row[0])

                return responses

            except aiosqlite.Error as e:
                self._logger.error(f"获取Bot最近回复失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def save_bot_message(
        self,
        group_id: str,
        user_id: str,
        message: str,
        response_to_message_id: Optional[int] = None,
        context_type: str = "normal",
        temperature: float = 0.7,
        language_style: Optional[str] = None,
        response_pattern: Optional[str] = None
    ) -> bool:
        """
        保存Bot发送的消息到数据库

        Args:
            group_id: 群组ID
            user_id: 回复的用户ID
            message: Bot的回复内容
            response_to_message_id: 回复的消息ID (来自raw_messages表)
            context_type: 上下文类型 (normal/creative/precise等)
            temperature: 使用的temperature参数
            language_style: 使用的语言风格
            response_pattern: 使用的回复模式

        Returns:
            bool: 是否成功保存
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    INSERT INTO bot_messages
                    (group_id, user_id, message, response_to_message_id, context_type,
                     temperature, language_style, response_pattern, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    group_id,
                    user_id,
                    message,
                    response_to_message_id,
                    context_type,
                    temperature,
                    language_style,
                    response_pattern,
                    time.time()
                ))

                await conn.commit()
                self._logger.debug(f" Bot消息已保存: group={group_id}, msg_preview={message[:50]}...")
                return True

            except aiosqlite.Error as e:
                self._logger.error(f"保存Bot消息失败: {e}", exc_info=True)
                return False
            finally:
                await cursor.close()

    async def get_bot_message_statistics(self, group_id: str, time_range_hours: int = 24) -> Dict[str, Any]:
        """
        获取Bot消息统计信息 (用于多样性分析)

        Args:
            group_id: 群组ID
            time_range_hours: 统计时间范围(小时)

        Returns:
            统计信息字典
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                cutoff_time = time.time() - (time_range_hours * 3600)

                # 统计消息总数
                await cursor.execute('''
                    SELECT COUNT(*) as total,
                           AVG(temperature) as avg_temp,
                           COUNT(DISTINCT language_style) as unique_styles,
                           COUNT(DISTINCT response_pattern) as unique_patterns
                    FROM bot_messages
                    WHERE group_id = ? AND timestamp > ?
                ''', (group_id, cutoff_time))

                row = await cursor.fetchone()

                # 获取最常用的风格和模式
                await cursor.execute('''
                    SELECT language_style, COUNT(*) as count
                    FROM bot_messages
                    WHERE group_id = ? AND timestamp > ? AND language_style IS NOT NULL
                    GROUP BY language_style
                    ORDER BY count DESC
                    LIMIT 5
                ''', (group_id, cutoff_time))

                top_styles = [{'style': row[0], 'count': row[1]} for row in await cursor.fetchall()]

                await cursor.execute('''
                    SELECT response_pattern, COUNT(*) as count
                    FROM bot_messages
                    WHERE group_id = ? AND timestamp > ? AND response_pattern IS NOT NULL
                    GROUP BY response_pattern
                    ORDER BY count DESC
                    LIMIT 5
                ''', (group_id, cutoff_time))

                top_patterns = [{'pattern': row[0], 'count': row[1]} for row in await cursor.fetchall()]

                return {
                    'total_messages': row[0] if row else 0,
                    'average_temperature': round(row[1], 2) if row and row[1] else 0.7,
                    'unique_styles_count': row[2] if row else 0,
                    'unique_patterns_count': row[3] if row else 0,
                    'top_styles': top_styles,
                    'top_patterns': top_patterns,
                    'time_range_hours': time_range_hours
                }

            except aiosqlite.Error as e:
                self._logger.error(f"获取Bot消息统计失败: {e}", exc_info=True)
                return {}
            finally:
                await cursor.close()

    # 黑话学习系统数据库操作方法

    async def get_jargon(self, chat_id: str, content: str) -> Optional[Dict[str, Any]]:
        """
        查询指定黑话

        Args:
            chat_id: 群组ID
            content: 黑话词条

        Returns:
            黑话记录字典或None
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    SELECT id, content, raw_content, meaning, is_jargon, count,
                           last_inference_count, is_complete, is_global, chat_id,
                           created_at, updated_at
                    FROM jargon
                    WHERE chat_id = ? AND content = ?
                ''', (chat_id, content))

                row = await cursor.fetchone()
                if not row:
                    return None

                return {
                    'id': row[0],
                    'content': row[1],
                    'raw_content': row[2],
                    'meaning': row[3],
                    'is_jargon': bool(row[4]) if row[4] is not None else None,
                    'count': row[5],
                    'last_inference_count': row[6],
                    'is_complete': bool(row[7]),
                    'is_global': bool(row[8]),
                    'chat_id': row[9],
                    'created_at': row[10],
                    'updated_at': row[11]
                }

            except aiosqlite.Error as e:
                logger.error(f"查询黑话失败: {e}", exc_info=True)
                return None
            finally:
                await cursor.close()

    async def insert_jargon(self, jargon: Dict[str, Any]) -> int:
        """
        插入新的黑话记录

        Args:
            jargon: 黑话数据字典

        Returns:
            插入记录的ID
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    INSERT INTO jargon
                    (content, raw_content, meaning, is_jargon, count, last_inference_count,
                     is_complete, is_global, chat_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    jargon.get('content'),
                    jargon.get('raw_content', '[]'),
                    jargon.get('meaning'),
                    jargon.get('is_jargon'),
                    jargon.get('count', 1),
                    jargon.get('last_inference_count', 0),
                    jargon.get('is_complete', False),
                    jargon.get('is_global', False),
                    jargon.get('chat_id'),
                    jargon.get('created_at'),
                    jargon.get('updated_at')
                ))

                jargon_id = cursor.lastrowid
                await conn.commit()
                logger.debug(f"插入黑话记录成功, ID: {jargon_id}")
                return jargon_id

            except aiosqlite.Error as e:
                logger.error(f"插入黑话失败: {e}", exc_info=True)
                raise
            finally:
                await cursor.close()

    async def update_jargon(self, jargon: Dict[str, Any]) -> bool:
        """
        更新现有黑话记录

        Args:
            jargon: 黑话数据字典(必须包含id)

        Returns:
            是否成功更新
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    UPDATE jargon
                    SET content = ?, raw_content = ?, meaning = ?, is_jargon = ?,
                        count = ?, last_inference_count = ?, is_complete = ?,
                        is_global = ?, updated_at = ?
                    WHERE id = ?
                ''', (
                    jargon.get('content'),
                    jargon.get('raw_content'),
                    jargon.get('meaning'),
                    jargon.get('is_jargon'),
                    jargon.get('count'),
                    jargon.get('last_inference_count'),
                    jargon.get('is_complete'),
                    jargon.get('is_global'),
                    jargon.get('updated_at'),
                    jargon.get('id')
                ))

                await conn.commit()
                logger.debug(f"更新黑话记录成功, ID: {jargon.get('id')}")
                return cursor.rowcount > 0

            except aiosqlite.Error as e:
                logger.error(f"更新黑话失败: {e}", exc_info=True)
                return False
            finally:
                await cursor.close()

    async def search_jargon(
        self,
        keyword: str,
        chat_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索黑话(用于LLM工具调用)

        Args:
            keyword: 搜索关键词
            chat_id: 群组ID (None表示搜索全局黑话)
            limit: 返回结果数量限制

        Returns:
            黑话记录列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 根据数据库类型选择占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                if chat_id:
                    # 搜索指定群组的黑话
                    query = f'''
                        SELECT id, content, meaning, is_jargon, count, is_complete
                        FROM jargon
                        WHERE chat_id = {placeholder} AND content LIKE {placeholder} AND is_jargon = 1
                        ORDER BY count DESC, updated_at DESC
                        LIMIT {placeholder}
                    '''
                    await cursor.execute(query, (chat_id, f'%{keyword}%', limit))
                else:
                    # 搜索全局黑话
                    query = f'''
                        SELECT id, content, meaning, is_jargon, count, is_complete
                        FROM jargon
                        WHERE content LIKE {placeholder} AND is_jargon = 1 AND is_global = 1
                        ORDER BY count DESC, updated_at DESC
                        LIMIT {placeholder}
                    '''
                    await cursor.execute(query, (f'%{keyword}%', limit))

                results = []
                for row in await cursor.fetchall():
                    results.append({
                        'id': row[0],
                        'content': row[1],
                        'meaning': row[2],
                        'is_jargon': bool(row[3]),
                        'count': row[4],
                        'is_complete': bool(row[5])
                    })

                return results

            except Exception as e:
                logger.error(f"搜索黑话失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_jargon_statistics(self, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取黑话学习统计信息

        Args:
            chat_id: 群组ID (None表示获取全局统计)

        Returns:
            统计信息字典
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 根据数据库类型选择占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                if chat_id:
                    # 群组统计
                    query = f'''
                        SELECT
                            COUNT(*) as total,
                            COUNT(CASE WHEN is_jargon = 1 THEN 1 END) as confirmed_jargon,
                            COUNT(CASE WHEN is_complete = 1 THEN 1 END) as completed,
                            SUM(count) as total_occurrences,
                            AVG(count) as avg_count
                        FROM jargon
                        WHERE chat_id = {placeholder}
                    '''
                    await cursor.execute(query, (chat_id,))
                else:
                    # 全局统计
                    await cursor.execute('''
                        SELECT
                            COUNT(*) as total,
                            COUNT(CASE WHEN is_jargon = 1 THEN 1 END) as confirmed_jargon,
                            COUNT(CASE WHEN is_complete = 1 THEN 1 END) as completed,
                            SUM(count) as total_occurrences,
                            AVG(count) as avg_count,
                            COUNT(DISTINCT chat_id) as active_groups
                        FROM jargon
                    ''')

                row = await cursor.fetchone()

                # 添加行数据验证
                if not row or len(row) < 5:
                    self._logger.warning(f"黑话统计数据行不完整 (期望至少5个字段，实际{len(row) if row else 0}个)，返回默认值")
                    return {
                        'total_candidates': 0,
                        'confirmed_jargon': 0,
                        'completed_inference': 0,
                        'total_occurrences': 0,
                        'average_count': 0,
                        'active_groups': 0
                    }

                stats = {
                    'total_candidates': int(row[0]) if row[0] else 0,
                    'confirmed_jargon': int(row[1]) if row[1] else 0,
                    'completed_inference': int(row[2]) if row[2] else 0,
                    'total_occurrences': int(row[3]) if row[3] else 0,
                    'average_count': round(float(row[4]), 1) if row[4] else 0
                }

                if not chat_id and len(row) > 5:
                    stats['active_groups'] = int(row[5]) if row[5] else 0

                return stats

            except Exception as e:
                logger.error(f"获取黑话统计失败: {e}", exc_info=True)
                return {
                    'total_candidates': 0,
                    'confirmed_jargon': 0,
                    'completed_inference': 0,
                    'total_occurrences': 0,
                    'average_count': 0
                }
            finally:
                await cursor.close()

    async def get_recent_jargon_list(
        self,
        chat_id: Optional[str] = None,
        limit: int = 20,
        only_confirmed: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取最近学习到的黑话列表

        Args:
            chat_id: 群组ID (None表示获取所有)
            limit: 返回数量限制
            only_confirmed: 是否只返回已确认的黑话

        Returns:
            黑话列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 根据数据库类型选择占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                query = '''
                    SELECT id, content, meaning, is_jargon, count,
                           last_inference_count, is_complete, chat_id, updated_at, is_global
                    FROM jargon
                    WHERE 1=1
                '''
                params = []

                if chat_id:
                    query += f' AND chat_id = {placeholder}'
                    params.append(chat_id)

                if only_confirmed:
                    query += ' AND is_jargon = 1'

                query += f' ORDER BY updated_at DESC LIMIT {placeholder}'
                params.append(limit)

                await cursor.execute(query, tuple(params))

                jargon_list = []
                for row in await cursor.fetchall():
                    try:
                        # 添加行数据验证
                        if len(row) < 10:
                            self._logger.warning(f"黑话记录行数据不完整 (期望10个字段，实际{len(row)}个)，跳过: {row}")
                            continue

                        jargon_list.append({
                            'id': row[0],
                            'content': row[1],
                            'meaning': row[2],
                            'is_jargon': bool(row[3]) if row[3] is not None else None,
                            'count': int(row[4]) if row[4] else 0,
                            'last_inference_count': int(row[5]) if row[5] else 0,
                            'is_complete': bool(row[6]),
                            'chat_id': row[7],
                            'updated_at': row[8],
                            'is_global': bool(row[9]) if row[9] is not None else False
                        })
                    except Exception as row_error:
                        self._logger.warning(f"处理黑话记录行时出错，跳过: {row_error}, row: {row}")
                        continue

                return jargon_list

            except Exception as e:
                logger.error(f"获取黑话列表失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def get_jargon_by_id(self, jargon_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取黑话记录

        Args:
            jargon_id: 黑话记录ID

        Returns:
            黑话记录或None
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 根据数据库类型选择占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                query = f'''
                    SELECT id, content, meaning, is_jargon, count,
                           last_inference_count, is_complete, chat_id, updated_at, is_global
                    FROM jargon
                    WHERE id = {placeholder}
                '''
                await cursor.execute(query, (jargon_id,))
                row = await cursor.fetchone()

                if row:
                    return {
                        'id': row[0],
                        'content': row[1],
                        'meaning': row[2],
                        'is_jargon': bool(row[3]) if row[3] is not None else None,
                        'count': row[4],
                        'last_inference_count': row[5],
                        'is_complete': bool(row[6]),
                        'chat_id': row[7],
                        'updated_at': row[8],
                        'is_global': bool(row[9]) if row[9] is not None else False
                    }
                return None

            except Exception as e:
                logger.error(f"获取黑话记录失败: {e}", exc_info=True)
                return None
            finally:
                await cursor.close()

    async def delete_jargon_by_id(self, jargon_id: int) -> bool:
        """
        根据ID删除黑话记录

        Args:
            jargon_id: 黑话记录ID

        Returns:
            是否成功删除
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 根据数据库类型选择占位符
                placeholder = '%s' if self.config.db_type.lower() == 'mysql' else '?'

                query = f'DELETE FROM jargon WHERE id = {placeholder}'
                await cursor.execute(query, (jargon_id,))
                await conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug(f"删除黑话记录成功, ID: {jargon_id}")
                return deleted

            except Exception as e:
                logger.error(f"删除黑话失败: {e}", exc_info=True)
                return False
            finally:
                await cursor.close()

    async def get_global_jargon_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取全局共享的黑话列表

        Args:
            limit: 返回数量限制

        Returns:
            全局黑话列表
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    SELECT id, content, meaning, is_jargon, count,
                           last_inference_count, is_complete, is_global, chat_id, updated_at
                    FROM jargon
                    WHERE is_jargon = 1 AND is_global = 1
                    ORDER BY count DESC, updated_at DESC
                    LIMIT ?
                ''', (limit,))

                jargon_list = []
                for row in await cursor.fetchall():
                    jargon_list.append({
                        'id': row[0],
                        'content': row[1],
                        'meaning': row[2],
                        'is_jargon': bool(row[3]),
                        'count': row[4],
                        'last_inference_count': row[5],
                        'is_complete': bool(row[6]),
                        'is_global': bool(row[7]),
                        'chat_id': row[8],
                        'updated_at': row[9]
                    })

                return jargon_list

            except aiosqlite.Error as e:
                logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
                return []
            finally:
                await cursor.close()

    async def set_jargon_global(self, jargon_id: int, is_global: bool) -> bool:
        """
        设置黑话的全局共享状态

        Args:
            jargon_id: 黑话记录ID
            is_global: 是否全局共享

        Returns:
            是否成功更新
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute('''
                    UPDATE jargon
                    SET is_global = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (is_global, jargon_id))

                await conn.commit()
                updated = cursor.rowcount > 0
                if updated:
                    logger.info(f"黑话全局状态已更新: ID={jargon_id}, is_global={is_global}")
                return updated

            except aiosqlite.Error as e:
                logger.error(f"更新黑话全局状态失败: {e}", exc_info=True)
                return False
            finally:
                await cursor.close()

    async def sync_global_jargon_to_group(self, target_chat_id: str) -> Dict[str, Any]:
        """
        将全局黑话同步到指定群组

        Args:
            target_chat_id: 目标群组ID

        Returns:
            同步结果统计
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                # 获取全局黑话列表
                await cursor.execute('''
                    SELECT content, meaning, count
                    FROM jargon
                    WHERE is_jargon = 1 AND is_global = 1 AND chat_id != ?
                ''', (target_chat_id,))

                global_jargon = await cursor.fetchall()

                synced_count = 0
                skipped_count = 0

                for content, meaning, count in global_jargon:
                    # 检查目标群组是否已存在该黑话
                    await cursor.execute('''
                        SELECT id FROM jargon
                        WHERE chat_id = ? AND content = ?
                    ''', (target_chat_id, content))

                    existing = await cursor.fetchone()

                    if existing:
                        # 已存在，跳过
                        skipped_count += 1
                    else:
                        # 不存在，同步到目标群组
                        await cursor.execute('''
                            INSERT INTO jargon
                            (content, raw_content, meaning, is_jargon, count, last_inference_count,
                             is_complete, is_global, chat_id, created_at, updated_at)
                            VALUES (?, '[]', ?, 1, 1, 0, 0, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ''', (content, meaning, target_chat_id))
                        synced_count += 1

                await conn.commit()

                logger.info(f"同步全局黑话到群组 {target_chat_id}: 同步 {synced_count} 条, 跳过 {skipped_count} 条")

                return {
                    'success': True,
                    'synced_count': synced_count,
                    'skipped_count': skipped_count,
                    'total_global': len(global_jargon)
                }

            except aiosqlite.Error as e:
                logger.error(f"同步全局黑话失败: {e}", exc_info=True)
                return {
                    'success': False,
                    'error': str(e),
                    'synced_count': 0,
                    'skipped_count': 0
                }
            finally:
                await cursor.close()

    async def batch_set_jargon_global(self, jargon_ids: List[int], is_global: bool) -> Dict[str, Any]:
        """
        批量设置黑话的全局共享状态

        Args:
            jargon_ids: 黑话记录ID列表
            is_global: 是否全局共享

        Returns:
            操作结果统计
        """
        async with self.get_db_connection() as conn:
            cursor = await conn.cursor()

            try:
                success_count = 0
                failed_count = 0

                for jid in jargon_ids:
                    try:
                        await cursor.execute('''
                            UPDATE jargon
                            SET is_global = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ? AND is_jargon = 1
                        ''', (is_global, jid))
                        if cursor.rowcount > 0:
                            success_count += 1
                        else:
                            failed_count += 1
                    except Exception:
                        failed_count += 1

                await conn.commit()

                logger.info(f"批量更新黑话全局状态: 成功 {success_count}, 失败 {failed_count}")

                return {
                    'success': True,
                    'success_count': success_count,
                    'failed_count': failed_count
                }

            except aiosqlite.Error as e:
                logger.error(f"批量更新黑话全局状态失败: {e}", exc_info=True)
                return {
                    'success': False,
                    'error': str(e),
                    'success_count': 0,
                    'failed_count': len(jargon_ids)
                }
            finally:
                await cursor.close()

    # ORM Repository 方法（新）

    async def get_learning_batch_by_id(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 batch_id 获取学习批次（使用 ORM）

        Args:
            batch_id: 批次 ID

        Returns:
            Optional[Dict]: 批次记录
        """
        if not self.db_engine:
            self._logger.warning("DatabaseEngine 未初始化，返回 None")
            return None

        try:
            async with self.db_engine.get_session() as session:
                repo = LearningBatchRepository(session)
                batch = await repo.get_learning_batch_by_id(batch_id)
                return batch.to_dict() if batch else None

        except Exception as e:
            self._logger.error(f"获取学习批次失败: {e}", exc_info=True)
            return None



