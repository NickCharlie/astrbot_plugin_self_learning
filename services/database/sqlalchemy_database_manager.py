"""
DomainRouter — 薄路由层，将所有数据库方法委托给领域 Facade

前身为 4308 行的单体 SQLAlchemyDatabaseManager，现已拆分为
11 个领域 Facade，本文件仅保留生命周期管理、会话/连接基础设施
以及方法路由。
"""
import os
import asyncio
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
from contextlib import asynccontextmanager

from astrbot.api import logger
from sqlalchemy.engine import URL

try:
    from ...config import DEFAULT_DB_TYPE, PluginConfig, normalize_db_type
    from ...core.database.engine import DatabaseEngine
except ImportError:
    from config import DEFAULT_DB_TYPE, PluginConfig, normalize_db_type
    from core.database.engine import DatabaseEngine


class SQLAlchemyDatabaseManager:
    """DomainRouter — 薄路由层，委托给 11 个领域 Facade。

    对外接口（方法签名、返回类型）与旧版完全一致，消费者无需任何改动。
    """

    # Lifecycle

    def __init__(self, config: PluginConfig, context=None):
        self.config = config
        self.context = context
        self.engine: Optional[DatabaseEngine] = None
        self._started = False
        self._starting = False
        self._start_lock = asyncio.Lock()

        # Facades（在 start() 中初始化）
        self._affection = None
        self._message = None
        self._learning = None
        self._jargon = None
        self._persona = None
        self._social = None
        self._expression = None
        self._psychological = None
        self._reinforcement = None
        self._metrics = None
        self._admin = None

    @property
    def is_ready(self) -> bool:
        """Return True if the database is fully started and facades are initialized."""
        return self._started

    async def start(self) -> bool:
        """启动数据库管理器（带并发保护）"""
        async with self._start_lock:
            if self._started:
                logger.debug("[DomainRouter] 已启动，跳过")
                return True

            if self._starting:
                logger.warning("[DomainRouter] 正在启动中，等待…")
                for _ in range(50):
                    await asyncio.sleep(0.1)
                    if self._started:
                        return True
                logger.error("[DomainRouter] 启动超时")
                return False

            db_type = None
            try:
                self._starting = True
                logger.info("[DomainRouter] 开始启动…")

                db_type = self._get_db_type()
                if await self._start_backend(db_type, self._get_database_url()):
                    return True

                if db_type == 'postgresql':
                    logger.warning(
                        "[DomainRouter] PostgreSQL 不可用，回退到 SQLite 本地数据库"
                    )
                    await self._close_engine()
                    if await self._start_backend(
                        'sqlite', self._get_sqlite_database_url()
                    ):
                        return True

                self._started = False
                self._starting = False
                return False

            except Exception as e:
                if db_type == 'postgresql':
                    logger.warning(
                        f"[DomainRouter] PostgreSQL 启动失败，回退到 SQLite: {e}"
                    )
                    await self._close_engine()
                    try:
                        if await self._start_backend(
                            'sqlite', self._get_sqlite_database_url()
                        ):
                            return True
                    except Exception as fallback_error:
                        logger.error(
                            f"[DomainRouter] SQLite 回退启动失败: {fallback_error}",
                            exc_info=True,
                        )
                        await self._close_engine()

                self._started = False
                self._starting = False
                logger.error(f"[DomainRouter] 启动失败: {e}", exc_info=True)
                return False

    async def stop(self) -> bool:
        """停止数据库管理器"""
        if not self._started:
            return True
        try:
            if self.engine:
                await self.engine.close()
            self._started = False
            logger.info("[DomainRouter] 数据库已停止")
            return True
        except Exception as e:
            logger.error(f"[DomainRouter] 停止失败: {e}")
            return False

    # Facade initialization

    def _init_facades(self):
        """初始化所有领域 Facade"""
        from .facades import (
            AffectionFacade, MessageFacade, LearningFacade,
            JargonFacade, PersonaFacade, SocialFacade,
            ExpressionFacade, PsychologicalFacade, ReinforcementFacade,
            MetricsFacade, AdminFacade,
        )
        self._affection = AffectionFacade(self.engine, self.config)
        self._message = MessageFacade(self.engine, self.config)
        self._learning = LearningFacade(self.engine, self.config)
        self._jargon = JargonFacade(self.engine, self.config)
        self._persona = PersonaFacade(self.engine, self.config)
        self._social = SocialFacade(self.engine, self.config)
        self._expression = ExpressionFacade(self.engine, self.config)
        self._psychological = PsychologicalFacade(self.engine, self.config)
        self._reinforcement = ReinforcementFacade(self.engine, self.config)
        self._metrics = MetricsFacade(self.engine, self.config)
        self._admin = AdminFacade(self.engine, self.config)
        logger.info("[DomainRouter] 11 个领域 Facade 已初始化")

    def _facade_or_none(
        self,
        facade_getter: Callable[[], Any],
        facade_name: str,
        operation: str = "",
    ):
        """Return a facade, recovering when the DB engine exists but facades are missing."""
        if self._starting:
            logger.warning(
                "[DomainRouter] 数据库仍在启动，"
                f"暂跳过数据库操作{f' ({operation})' if operation else ''}"
            )
            return None

        if not self._started or self.engine is None:
            logger.warning(
                "[DomainRouter] 数据库尚未启动，"
                f"暂跳过数据库操作{f' ({operation})' if operation else ''}"
            )
            return None

        facade = facade_getter()
        if facade is not None:
            return facade

        try:
            self._init_facades()
        except Exception as e:
            logger.warning(
                f"[DomainRouter] {facade_name} 初始化失败"
                f"{f' ({operation})' if operation else ''}: {e}",
                exc_info=True,
            )
            return None

        facade = facade_getter()
        if facade is None:
            logger.warning(
                f"[DomainRouter] {facade_name} 不可用，"
                f"跳过数据库操作{f' ({operation})' if operation else ''}"
            )
        return facade

    @staticmethod
    def _empty_message_statistics() -> Dict[str, Any]:
        return {
            'total_messages': 0,
            'raw_messages': 0,
            'filtered_messages': 0,
            'bot_messages': 0,
        }

    @staticmethod
    def _empty_expression_patterns_statistics() -> Dict[str, Any]:
        return {
            'total_patterns': 0,
            'groups_with_patterns': 0,
        }

    @staticmethod
    def _empty_trends_data() -> Dict[str, Any]:
        return {
            'daily_messages': {},
            'recent_batches': [],
        }

    @staticmethod
    def _empty_jargon_statistics() -> Dict[str, Any]:
        return {
            'total_candidates': 0,
            'confirmed_jargon': 0,
            'completed_inference': 0,
            'total_occurrences': 0,
            'average_count': 0,
            'active_groups': 0,
        }

    async def _call_facade(
        self,
        facade_getter: Callable[[], Any],
        facade_name: str,
        operation: str,
        default: Any,
        *args,
        **kwargs,
    ):
        """Call a facade method if it is ready, otherwise return default."""
        facade = self._facade_or_none(facade_getter, facade_name, operation)
        if facade is None:
            return default
        method = getattr(facade, operation, None)
        if not callable(method):
            logger.warning(f"[DomainRouter] {facade_name} 缺少方法: {operation}")
            return default
        return await method(*args, **kwargs)

    async def _call_learning(self, operation: str, default: Any, *args, **kwargs):
        """Call a LearningFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._learning,
            "LearningFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    async def _call_jargon(self, operation: str, default: Any, *args, **kwargs):
        """Call a JargonFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._jargon,
            "JargonFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    async def _call_message(self, operation: str, default: Any, *args, **kwargs):
        """Call a MessageFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._message,
            "MessageFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    async def _call_expression(self, operation: str, default: Any, *args, **kwargs):
        """Call an ExpressionFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._expression,
            "ExpressionFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    async def _call_reinforcement(self, operation: str, default: Any, *args, **kwargs):
        """Call a ReinforcementFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._reinforcement,
            "ReinforcementFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    async def _call_metrics(self, operation: str, default: Any, *args, **kwargs):
        """Call a MetricsFacade method if it is ready, otherwise return default."""
        return await self._call_facade(
            lambda: self._metrics,
            "MetricsFacade",
            operation,
            default,
            *args,
            **kwargs,
        )

    # Infrastructure: database URL

    async def _start_backend(self, db_type: str, db_url: str) -> bool:
        """启动指定数据库后端并同步表结构。"""
        if db_type == 'mysql':
            await self._ensure_mysql_database_exists()
        elif db_type == 'postgresql':
            await self._ensure_postgresql_database_exists()
            await self._ensure_postgresql_schema_exists()

        self.engine = DatabaseEngine(db_url, echo=False)
        logger.info(f"[DomainRouter] 数据库引擎已创建 ({db_type})")

        await self.engine.create_tables(enable_auto_migration=True)

        if await self.engine.health_check():
            self._init_facades()
            self._started = True
            self._starting = False
            logger.info(f"[DomainRouter] 数据库启动成功 ({db_type})")
            return True

        logger.error(f"[DomainRouter] 数据库健康检查失败 ({db_type})")
        await self._close_engine()
        return False

    async def _close_engine(self):
        """关闭当前引擎，供失败重试/回退使用。"""
        if self.engine:
            await self.engine.close()
            self.engine = None

    def _get_db_type(self) -> str:
        """获取标准化数据库类型。"""
        raw_db_type = getattr(self.config, 'db_type', DEFAULT_DB_TYPE)
        db_type = normalize_db_type(raw_db_type)
        if db_type is None:
            raise ValueError(f"不支持的数据库类型: {raw_db_type}")
        return db_type

    def _get_database_url(self) -> str:
        """获取数据库连接 URL"""
        db_type = self._get_db_type()
        if db_type == 'mysql':
            host = getattr(self.config, 'mysql_host', 'localhost')
            port = getattr(self.config, 'mysql_port', 3306)
            user = getattr(self.config, 'mysql_user', 'root')
            password = getattr(self.config, 'mysql_password', '')
            database = getattr(self.config, 'mysql_database', 'astrbot_self_learning')
            return URL.create(
                'mysql+aiomysql',
                username=user or None,
                password=password or None,
                host=host,
                port=port,
                database=database,
            ).render_as_string(hide_password=False)

        if db_type == 'postgresql':
            host = getattr(self.config, 'postgresql_host', 'localhost')
            port = getattr(self.config, 'postgresql_port', 5432)
            user = getattr(self.config, 'postgresql_user', 'postgres')
            password = getattr(self.config, 'postgresql_password', '')
            database = getattr(self.config, 'postgresql_database', 'astrbot_self_learning')
            schema = getattr(self.config, 'postgresql_schema', 'public') or 'public'
            query = {'search_path': schema} if schema != 'public' else {}
            return URL.create(
                'postgresql+asyncpg',
                username=user or None,
                password=password or None,
                host=host,
                port=port,
                database=database,
                query=query,
            ).render_as_string(hide_password=False)

        if db_type != 'sqlite':
            raise ValueError(f"不支持的数据库类型: {db_type}")

        return self._get_sqlite_database_url()

    def _get_sqlite_database_url(self) -> str:
        """获取 SQLite 回退数据库连接 URL。"""
        db_path = getattr(self.config, 'messages_db_path', None)
        if not db_path:
            db_path = os.path.join(self.config.data_dir, 'messages.db')
        db_path = os.path.expandvars(os.path.expanduser(str(db_path)))
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        return URL.create(
            'sqlite+aiosqlite',
            database=Path(db_path).as_posix(),
        ).render_as_string(hide_password=False)

    async def _ensure_mysql_database_exists(self):
        """确保 MySQL 数据库存在

        使用 aiomysql 直连 MySQL 服务器以检查/创建目标数据库。
        显式禁用 SSL 以避免 MySQL 8 默认 TLS 握手导致的
        struct.unpack 解包异常。
        """
        import aiomysql
        host = getattr(self.config, 'mysql_host', 'localhost')
        port = getattr(self.config, 'mysql_port', 3306)
        user = getattr(self.config, 'mysql_user', 'root')
        password = getattr(self.config, 'mysql_password', '')
        database = getattr(self.config, 'mysql_database', 'astrbot_self_learning')

        try:
            conn = await asyncio.wait_for(
                aiomysql.connect(
                    host=host, port=port, user=user,
                    password=password, charset='utf8mb4',
                    ssl=False, connect_timeout=10,
                ),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.error("[DomainRouter] 连接 MySQL 超时 (15s)")
            raise
        except Exception as e:
            logger.error(f"[DomainRouter] 连接 MySQL 失败: {e}")
            raise

        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                    (database,),
                )
                if not await cursor.fetchone():
                    logger.info(f"[DomainRouter] 数据库 {database} 不存在，正在创建...")
                    await cursor.execute(
                        f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    await conn.commit()
                    logger.info(f"[DomainRouter] 数据库 {database} 创建成功")
        except Exception as e:
            logger.error(f"[DomainRouter] 确保 MySQL 数据库存在失败: {e}")
            raise
        finally:
            conn.close()

    async def _ensure_postgresql_database_exists(self):
        """确保 PostgreSQL 数据库存在。"""
        try:
            import asyncpg
        except ImportError as e:
            raise RuntimeError(
                "缺少 PostgreSQL 异步驱动 asyncpg，请先安装依赖或使用打包版依赖"
            ) from e

        host = getattr(self.config, 'postgresql_host', 'localhost')
        port = getattr(self.config, 'postgresql_port', 5432)
        user = getattr(self.config, 'postgresql_user', 'postgres')
        password = getattr(self.config, 'postgresql_password', '')
        database = getattr(self.config, 'postgresql_database', 'astrbot_self_learning')

        conn = await self._connect_postgresql(asyncpg, database='postgres')
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                database,
            )
            if not exists:
                logger.info(f"[DomainRouter] PostgreSQL 数据库 {database} 不存在，正在创建...")
                await conn.execute(
                    f"CREATE DATABASE {self._quote_postgresql_identifier(database)}"
                )
                logger.info(f"[DomainRouter] PostgreSQL 数据库 {database} 创建成功")
        except Exception as e:
            logger.error(
                f"[DomainRouter] 确保 PostgreSQL 数据库存在失败 "
                f"({user}@{host}:{port}/{database}): {e}"
            )
            raise
        finally:
            await conn.close()

    async def _ensure_postgresql_schema_exists(self):
        """确保 PostgreSQL schema 存在。"""
        schema = getattr(self.config, 'postgresql_schema', 'public') or 'public'
        if schema == 'public':
            return

        try:
            import asyncpg
        except ImportError as e:
            raise RuntimeError(
                "缺少 PostgreSQL 异步驱动 asyncpg，请先安装依赖或使用打包版依赖"
            ) from e

        database = getattr(self.config, 'postgresql_database', 'astrbot_self_learning')
        conn = await self._connect_postgresql(asyncpg, database=database)
        try:
            await conn.execute(
                f"CREATE SCHEMA IF NOT EXISTS {self._quote_postgresql_identifier(schema)}"
            )
            logger.info(f"[DomainRouter] PostgreSQL schema 已就绪: {schema}")
        except Exception as e:
            logger.error(f"[DomainRouter] 确保 PostgreSQL schema 存在失败: {e}")
            raise
        finally:
            await conn.close()

    async def _connect_postgresql(self, asyncpg, database: str):
        """连接 PostgreSQL，统一超时和错误日志。"""
        host = getattr(self.config, 'postgresql_host', 'localhost')
        port = getattr(self.config, 'postgresql_port', 5432)
        user = getattr(self.config, 'postgresql_user', 'postgres')
        password = getattr(self.config, 'postgresql_password', '')
        try:
            return await asyncio.wait_for(
                asyncpg.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    timeout=10,
                ),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.error("[DomainRouter] 连接 PostgreSQL 超时 (15s)")
            raise
        except Exception as e:
            logger.error(f"[DomainRouter] 连接 PostgreSQL 失败: {e}")
            raise

    @staticmethod
    def _quote_postgresql_identifier(identifier: str) -> str:
        """安全引用 PostgreSQL 标识符。"""
        if not identifier or '\x00' in identifier:
            raise ValueError("PostgreSQL 标识符不能为空或包含 NUL 字符")
        return '"' + identifier.replace('"', '""') + '"'

    # Infrastructure: session

    @asynccontextmanager
    async def get_session(self):
        """获取 ORM 会话（async context manager）"""
        if not self.engine:
            if self._starting:
                logger.debug("[DomainRouter] 等待 engine 创建…")
                for _ in range(30):
                    await asyncio.sleep(0.1)
                    if self.engine:
                        break
                if not self.engine:
                    raise RuntimeError("数据库管理器启动超时，engine未创建")
            else:
                raise RuntimeError("数据库管理器未启动，engine不存在")

        if not self._started:
            logger.debug("[DomainRouter] get_session: _started=False 但 engine 存在，继续执行")

        session = self.engine.get_session()
        try:
            async with session:
                yield session
        except Exception:
            raise

    # Domain delegates: AffectionFacade

    async def get_user_affection(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._affection.get_user_affection(group_id, user_id)

    async def update_user_affection(
        self, group_id: str, user_id: str, new_level: int,
        change_reason: str = "", bot_mood: str = "",
    ) -> bool:
        return await self._affection.update_user_affection(
            group_id, user_id, new_level, change_reason, bot_mood,
        )

    async def get_all_user_affections(self, group_id: str) -> List[Dict[str, Any]]:
        return await self._affection.get_all_user_affections(group_id)

    async def get_total_affection(self, group_id: str) -> int:
        return await self._affection.get_total_affection(group_id)

    async def save_bot_mood(
        self, group_id: str, mood_type: str, mood_intensity: float,
        mood_description: str, duration_hours: int = 24,
    ) -> bool:
        return await self._affection.save_bot_mood(
            group_id, mood_type, mood_intensity, mood_description, duration_hours,
        )

    async def get_current_bot_mood(self, group_id: str) -> Optional[Dict[str, Any]]:
        return await self._affection.get_current_bot_mood(group_id)

    # Domain delegates: MessageFacade

    async def save_raw_message(self, message_data) -> int:
        return await self._message.save_raw_message(message_data)

    async def get_recent_raw_messages(
        self, group_id: str, limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_recent_raw_messages(group_id, limit)

    async def get_unprocessed_messages(
        self, limit: Optional[int] = None, group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_unprocessed_messages(limit, group_id)

    async def mark_messages_processed(self, message_ids: List[int]) -> bool:
        return await self._message.mark_messages_processed(message_ids)

    async def get_messages_by_timerange(
        self, group_id: str, start_time: int, end_time: int, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_messages_by_timerange(
            group_id, start_time, end_time, limit,
        )

    async def get_messages_by_group_and_timerange(
        self, group_id: str, start_time: int, end_time: int, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_messages_by_group_and_timerange(
            group_id, start_time, end_time, limit,
        )

    async def get_messages_for_replay(
        self, group_id: str, days: int = 30, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_messages_for_replay(group_id, days, limit)

    async def get_recent_filtered_messages(
        self, group_id: str, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_recent_filtered_messages(group_id, limit)

    async def get_filtered_messages_for_learning(
        self, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self._message.get_filtered_messages_for_learning(limit)

    async def add_filtered_message(self, filtered_data: Dict[str, Any]) -> int:
        return await self._message.add_filtered_message(filtered_data)

    async def save_bot_message(
        self, group_id: str, message: str, timestamp: int = None,
    ) -> bool:
        return await self._message.save_bot_message(group_id, message, timestamp)

    async def get_recent_bot_responses(
        self, group_id: str, limit: int = 10,
    ) -> List[str]:
        return await self._message.get_recent_bot_responses(group_id, limit)

    async def get_message_statistics(
        self, group_id: str = None,
    ) -> Dict[str, Any]:
        if group_id is None:
            default = self._empty_message_statistics()
        else:
            default = {
                'total_messages': 0,
                'unprocessed_messages': 0,
                'filtered_messages': 0,
                'raw_messages': 0,
                'group_id': group_id,
            }
        return await self._call_message("get_message_statistics", default, group_id)

    async def get_messages_statistics(self) -> Dict[str, Any]:
        return await self._call_message(
            "get_messages_statistics",
            self._empty_message_statistics(),
        )

    async def get_group_messages_statistics(self, group_id: str) -> Dict[str, Any]:
        return await self._message.get_group_messages_statistics(group_id)

    async def get_group_user_statistics(
        self, group_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        return await self._message.get_group_user_statistics(group_id)

    async def get_groups_for_social_analysis(self) -> List[Dict[str, Any]]:
        return await self._message.get_groups_for_social_analysis()

    # Domain delegates: LearningFacade

    async def add_persona_learning_review(
        self,
        review_data: Dict[str, Any] = None,
        *,
        group_id: str = None,
        proposed_content: str = None,
        learning_source: str = '',
        confidence_score: float = 0.5,
        raw_analysis: str = '',
        metadata: Dict[str, Any] = None,
        original_content: str = '',
        new_content: str = '',
    ) -> int:
        """兼容新旧两种调用方式：单 dict 或关键字参数。"""
        if review_data is None:
            review_data = {
                'group_id': group_id or '',
                'proposed_content': proposed_content or '',
                'update_type': learning_source,
                'confidence_score': confidence_score,
                'reason': raw_analysis,
                'metadata': metadata or {},
                'original_content': original_content,
                'new_content': new_content,
            }
        return await self._call_learning("add_persona_learning_review", 0, review_data)

    async def save_persona_change_snapshot(
        self, snapshot_data: Dict[str, Any],
    ) -> int:
        return await self._call_learning(
            "save_persona_change_snapshot",
            0,
            snapshot_data,
        )

    async def get_persona_change_snapshot(
        self, review_source: str, review_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await self._call_learning(
            "get_persona_change_snapshot",
            None,
            review_source,
            review_id,
        )

    async def get_pending_persona_update_records(self) -> List[Dict[str, Any]]:
        return await self._call_learning("get_pending_persona_update_records", [])

    async def save_persona_update_record(self, record_data: Dict[str, Any]) -> int:
        return await self._call_learning("save_persona_update_record", 0, record_data)

    async def delete_persona_update_record(self, record_id: int) -> bool:
        return await self._call_learning("delete_persona_update_record", False, record_id)

    async def get_persona_update_record_by_id(
        self, record_id: int,
    ) -> Optional[Dict[str, Any]]:
        return await self._call_learning(
            "get_persona_update_record_by_id",
            None,
            record_id,
        )

    async def get_reviewed_persona_update_records(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self._call_learning(
            "get_reviewed_persona_update_records",
            [],
            limit=limit, offset=offset, status_filter=status_filter,
        )

    async def update_persona_update_record_status(
        self, record_id: int, status: str, comment: str = None,
    ) -> bool:
        return await self._call_learning(
            "update_persona_update_record_status",
            False,
            record_id, status, comment,
        )

    async def create_style_learning_review(
        self, review_data: Dict[str, Any],
    ) -> int:
        return await self._call_learning("create_style_learning_review", 0, review_data)

    async def get_pending_style_reviews(
        self, limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning("get_pending_style_reviews", [], limit, offset)

    async def get_reviewed_style_learning_updates(
        self, limit: int = 50, offset: int = 0, status_filter: str = None,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning(
            "get_reviewed_style_learning_updates",
            [],
            limit=limit, offset=offset, status_filter=status_filter,
        )

    async def update_style_review_status(
        self, review_id: int, status: str, reviewer_comment: str = '',
    ) -> bool:
        return await self._call_learning(
            "update_style_review_status",
            False,
            review_id, status, reviewer_comment,
        )

    async def delete_style_review_by_id(self, review_id: int) -> bool:
        return await self._call_learning("delete_style_review_by_id", False, review_id)

    async def get_approved_few_shots(
        self, group_id: str, limit: int = 3,
    ) -> List[str]:
        return await self._call_learning("get_approved_few_shots", [], group_id, limit)

    async def get_pending_persona_learning_reviews(
        self, limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning(
            "get_pending_persona_learning_reviews",
            [],
            limit,
            offset,
        )

    async def get_reviewed_persona_learning_updates(
        self, limit: int = 50, offset: int = 0, status_filter: str = None,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning(
            "get_reviewed_persona_learning_updates",
            [],
            limit=limit, offset=offset, status_filter=status_filter,
        )

    async def delete_persona_learning_review_by_id(self, review_id: int) -> bool:
        return await self._call_learning(
            "delete_persona_learning_review_by_id",
            False,
            review_id,
        )

    async def get_persona_learning_review_by_id(
        self, review_id: int,
    ) -> Optional[Dict[str, Any]]:
        return await self._call_learning(
            "get_persona_learning_review_by_id",
            None,
            review_id,
        )

    async def update_persona_learning_review_status(
        self, review_id: int, status: str, comment: str = None,
        modified_content: str = None,
    ) -> bool:
        return await self._call_learning(
            "update_persona_learning_review_status",
            False,
            review_id, status, comment, modified_content,
        )

    async def get_learning_batch_history(
        self, group_id: str = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning(
            "get_learning_batch_history",
            [],
            group_id,
            limit,
        )

    async def get_recent_learning_batches(
        self, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning("get_recent_learning_batches", [], limit)

    async def get_learning_sessions(self, group_id: str) -> List[Dict[str, Any]]:
        return await self._call_learning("get_learning_sessions", [], group_id)

    async def get_recent_learning_sessions(
        self, days: int = 7,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning("get_recent_learning_sessions", [], days)

    async def save_learning_session_record(
        self, group_id: str, session_data: Dict[str, Any],
    ) -> bool:
        return await self._call_learning(
            "save_learning_session_record",
            False,
            group_id,
            session_data,
        )

    async def save_learning_performance_record(
        self, group_id: str, performance_data: Dict[str, Any],
    ) -> bool:
        return await self._call_learning(
            "save_learning_performance_record",
            False,
            group_id, performance_data,
        )

    async def count_pending_persona_updates(self) -> int:
        return await self._call_learning("count_pending_persona_updates", 0)

    async def count_style_learning_patterns(self) -> int:
        return await self._call_learning("count_style_learning_patterns", 0)

    async def count_refined_messages(self) -> int:
        return await self._call_learning("count_refined_messages", 0)

    async def get_style_learning_statistics(self) -> Dict[str, Any]:
        return await self._call_learning("get_style_learning_statistics", {})

    async def get_style_progress_data(
        self, group_id: str = None,
    ) -> List[Dict[str, Any]]:
        return await self._call_learning("get_style_progress_data", [], group_id)

    async def get_learning_patterns_data(
        self, group_id: str = None,
    ) -> Dict[str, Any]:
        return await self._call_learning("get_learning_patterns_data", {}, group_id)

    # Domain delegates: JargonFacade

    async def get_jargon(self, chat_id: str, content: str) -> Optional[Dict[str, Any]]:
        return await self._call_jargon("get_jargon", None, chat_id, content)

    async def insert_jargon(self, jargon_data: Dict[str, Any]) -> Optional[int]:
        return await self._call_jargon("insert_jargon", None, jargon_data)

    async def update_jargon(self, jargon_data: Dict[str, Any]) -> bool:
        return await self._call_jargon("update_jargon", False, jargon_data)

    async def get_jargon_statistics(self, group_id: str = None) -> Dict[str, Any]:
        return await self._call_jargon(
            "get_jargon_statistics",
            self._empty_jargon_statistics(),
            group_id,
        )

    async def get_recent_jargon_list(
        self, group_id: str = None, chat_id: str = None,
        limit: int = 50, offset: int = 0, only_confirmed: bool = False,
        pending_only: bool = False, global_only: bool = False, local_only: bool = False,
    ) -> List[Dict[str, Any]]:
        return await self._call_jargon(
            "get_recent_jargon_list",
            [],
            group_id, chat_id, limit, offset, only_confirmed, pending_only,
            global_only, local_only,
        )

    async def get_jargon_count(
        self, chat_id: str = None, only_confirmed: bool = False,
        pending_only: bool = False, global_only: bool = False, local_only: bool = False,
    ) -> int:
        return await self._call_jargon(
            "get_jargon_count",
            0,
            chat_id,
            only_confirmed,
            pending_only,
            global_only,
            local_only,
        )

    async def search_jargon(
        self, keyword: str, chat_id: str = None,
        confirmed_only: bool = False, pending_only: bool = False,
        global_only: bool = False, local_only: bool = False, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return await self._call_jargon(
            "search_jargon",
            [],
            keyword=keyword, chat_id=chat_id,
            confirmed_only=confirmed_only, pending_only=pending_only,
            global_only=global_only, local_only=local_only, limit=limit,
        )

    async def get_jargon_by_id(self, jargon_id: int) -> Optional[Dict[str, Any]]:
        return await self._call_jargon("get_jargon_by_id", None, jargon_id)

    async def delete_jargon_by_id(self, jargon_id: int) -> bool:
        return await self._call_jargon("delete_jargon_by_id", False, jargon_id)

    async def set_jargon_global(self, jargon_id: int, is_global: bool) -> bool:
        return await self._call_jargon(
            "set_jargon_global",
            False,
            jargon_id,
            is_global,
        )

    async def sync_global_jargon_to_group(self, target_chat_id: str) -> int:
        return await self._call_jargon(
            "sync_global_jargon_to_group",
            0,
            target_chat_id,
        )

    async def save_or_update_jargon(
        self, chat_id: str, content: str, jargon_data: Dict[str, Any],
    ) -> Optional[int]:
        return await self._call_jargon(
            "save_or_update_jargon",
            None,
            chat_id, content, jargon_data,
        )

    async def get_global_jargon_list(
        self, limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._call_jargon("get_global_jargon_list", [], limit)

    async def get_jargon_groups(self) -> List[Dict[str, Any]]:
        return await self._call_jargon("get_jargon_groups", [])

    # Domain delegates: PersonaFacade

    async def backup_persona(self, group_id: str, backup_data: Dict[str, Any]) -> bool:
        backup_data.setdefault('group_id', group_id)
        return await self._persona.backup_persona(backup_data)

    async def get_persona_backups(self, limit: int = 10) -> List[Dict[str, Any]]:
        return await self._persona.get_persona_backups(limit)

    async def restore_persona_backup(
        self, backup_id: int,
    ) -> Optional[Dict[str, Any]]:
        return await self._persona.restore_persona_backup(backup_id)

    async def get_persona_update_history(
        self, group_id: str = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return await self._persona.get_persona_update_history(group_id, limit)

    # Domain delegates: SocialFacade

    async def load_user_profile(self, qq_id: str) -> Optional[Dict[str, Any]]:
        return await self._social.load_user_profile(qq_id)

    async def save_user_profile(
        self, qq_id: str, profile_data: Dict[str, Any],
    ) -> bool:
        return await self._social.save_user_profile(qq_id, profile_data)

    async def load_user_preferences(
        self, user_id: str, group_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await self._social.load_user_preferences(user_id, group_id)

    async def save_user_preferences(
        self, user_id: str, group_id: str, prefs: Dict[str, Any],
    ) -> bool:
        return await self._social.save_user_preferences(user_id, group_id, prefs)

    async def get_social_relations_by_group(
        self, group_id: str,
    ) -> List[Dict[str, Any]]:
        return await self._social.get_social_relations_by_group(group_id)

    async def get_social_relationships(
        self, group_id: str,
    ) -> List[Dict[str, Any]]:
        return await self._social.get_social_relationships(group_id)

    async def load_social_graph(self, group_id: str) -> List[Dict[str, Any]]:
        return await self._social.load_social_graph(group_id)

    async def save_social_relation(
        self, group_id: str, relation_data: Dict[str, Any],
    ) -> bool:
        return await self._social.save_social_relation(group_id, relation_data)

    async def get_user_social_relations(
        self, group_id: str, user_id: str,
    ) -> Dict[str, Any]:
        return await self._social.get_user_social_relations(group_id, user_id)

    # Domain delegates: ExpressionFacade

    async def get_all_expression_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        return await self._expression.get_all_expression_patterns()

    async def get_expression_patterns_statistics(self) -> Dict[str, Any]:
        return await self._call_expression(
            "get_expression_patterns_statistics",
            self._empty_expression_patterns_statistics(),
        )

    async def get_group_expression_patterns(
        self, group_id: str, limit: int = None,
    ) -> List[Dict[str, Any]]:
        return await self._expression.get_group_expression_patterns(group_id, limit)

    async def get_recent_week_expression_patterns(
        self, group_id: str = None, limit: int = 50, hours: int = 168,
    ) -> List[Dict[str, Any]]:
        return await self._expression.get_recent_week_expression_patterns(
            group_id, limit, hours,
        )

    async def load_style_profile(
        self, profile_name: str,
    ) -> Optional[Dict[str, Any]]:
        return await self._expression.load_style_profile(profile_name)

    async def save_style_profile(
        self, profile_name: str, profile_data: Dict[str, Any],
    ) -> bool:
        return await self._expression.save_style_profile(profile_name, profile_data)

    async def save_style_learning_record(
        self, record_data: Dict[str, Any],
    ) -> bool:
        return await self._expression.save_style_learning_record(record_data)

    async def save_language_style_pattern(
        self, language_style: str, pattern_data: Dict[str, Any],
    ) -> bool:
        return await self._expression.save_language_style_pattern(
            language_style, pattern_data,
        )

    # Domain delegates: PsychologicalFacade

    async def load_emotion_profile(
        self, user_id: str, group_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await self._psychological.load_emotion_profile(user_id, group_id)

    async def save_emotion_profile(
        self, user_id: str, group_id: str, profile: Dict[str, Any],
    ) -> bool:
        return await self._psychological.save_emotion_profile(
            user_id, group_id, profile,
        )

    # Domain delegates: ReinforcementFacade

    async def get_learning_history_for_reinforcement(
        self, group_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return await self._reinforcement.get_learning_history_for_reinforcement(
            group_id, limit,
        )

    async def save_reinforcement_learning_result(
        self, group_id: str, result_data: Dict[str, Any],
    ) -> bool:
        return await self._reinforcement.save_reinforcement_learning_result(
            group_id, result_data,
        )

    async def get_persona_fusion_history(
        self, group_id: str, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return await self._reinforcement.get_persona_fusion_history(group_id, limit)

    async def save_persona_fusion_result(
        self, group_id: str, fusion_data: Dict[str, Any],
    ) -> bool:
        return await self._reinforcement.save_persona_fusion_result(
            group_id, fusion_data,
        )

    async def get_learning_performance_history(
        self, group_id: str, limit: int = 30,
    ) -> List[Dict[str, Any]]:
        return await self._call_reinforcement(
            "get_learning_performance_history",
            [],
            group_id,
            limit,
        )

    async def save_strategy_optimization_result(
        self, group_id: str, optimization_data: Dict[str, Any],
    ) -> bool:
        return await self._reinforcement.save_strategy_optimization_result(
            group_id, optimization_data,
        )

    # Domain delegates: MetricsFacade

    async def get_group_statistics(
        self, group_id: str = None,
    ) -> Dict[str, Any]:
        return await self._metrics.get_group_statistics(group_id)

    async def get_detailed_metrics(
        self, group_id: str = None,
    ) -> Dict[str, Any]:
        return await self._metrics.get_detailed_metrics(group_id)

    async def get_trends_data(self) -> Dict[str, Any]:
        return await self._call_metrics("get_trends_data", self._empty_trends_data())

    # Domain delegates: AdminFacade

    async def clear_all_messages_data(self) -> bool:
        return await self._admin.clear_all_messages_data()

    async def export_messages_learning_data(
        self, group_id: str = None,
    ) -> Dict[str, Any]:
        return await self._admin.export_messages_learning_data(group_id)

    async def clear_messages_data(self) -> Dict[str, Any]:
        return await self._admin.clear_messages_data()

    async def clear_persona_reviews_data(self) -> Dict[str, Any]:
        return await self._admin.clear_persona_reviews_data()

    async def clear_style_learning_data(self) -> Dict[str, Any]:
        return await self._admin.clear_style_learning_data()

    async def clear_jargon_data(self) -> Dict[str, Any]:
        return await self._admin.clear_jargon_data()

    async def clear_learning_history_data(self) -> Dict[str, Any]:
        return await self._admin.clear_learning_history_data()

    async def clear_all_plugin_data(self) -> Dict[str, Any]:
        return await self._admin.clear_all_plugin_data()

    async def get_data_statistics(self) -> Dict[str, int]:
        return await self._admin.get_data_statistics()
