"""
增强型数据库管理器 - 使用 SQLAlchemy 和 Repository 模式
与现有 DatabaseManager 接口兼容，可通过配置切换
"""
import time
import asyncio

from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from astrbot.api import logger

from ..config import PluginConfig
from ..core.database.engine import DatabaseEngine
from ..repositories import (
    # 好感度系统
    AffectionRepository,
    InteractionRepository,
    ConversationHistoryRepository,
    DiversityRepository,
    # 记忆系统
    MemoryRepository,
    MemoryEmbeddingRepository,
    MemorySummaryRepository,
    # 心理状态系统
    PsychologicalStateRepository,
    PsychologicalComponentRepository,
    PsychologicalHistoryRepository,
    # 社交关系系统
    SocialProfileRepository,
    SocialRelationComponentRepository,
    SocialRelationHistoryRepository,
)


class SQLAlchemyDatabaseManager:
    """
    基于 SQLAlchemy 的增强型数据库管理器

    特性:
    1. 使用 SQLAlchemy ORM 和 Repository 模式
    2. 与现有 DatabaseManager 接口兼容
    3. 支持 SQLite 和 MySQL
    4. 更好的类型安全和错误处理
    5. 统一的数据访问层

    用法:
        # 在配置中启用
        config.use_sqlalchemy = True

        # 创建管理器
        db_manager = SQLAlchemyDatabaseManager(config)
        await db_manager.start()

        # 使用Repository
        async with db_manager.get_session() as session:
            affection_repo = AffectionRepository(session)
            affection = await affection_repo.get_by_group_and_user(group_id, user_id)
    """

    def __init__(self, config: PluginConfig, context=None):
        """
        初始化数据库管理器

        Args:
            config: 插件配置
            context: 上下文（可选）
        """
        self.config = config
        self.context = context
        self.engine: Optional[DatabaseEngine] = None
        self._started = False
        self._starting = False
        self._start_lock = asyncio.Lock()

        # 创建传统 DatabaseManager 实例用于委托未实现的方法
        from .database_manager import DatabaseManager
        self._legacy_db: Optional[DatabaseManager] = None
        try:
            # ✨ 传入 skip_table_init=True，让传统数据库管理器跳过表初始化
            # 因为 SQLAlchemy ORM 会通过 create_tables() 自动创建和迁移所有表
            self._legacy_db = DatabaseManager(config, context, skip_table_init=True)
            logger.info("[SQLAlchemyDBManager] 初始化完成（包含传统数据库管理器后备，跳过表初始化）")
        except Exception as e:
            logger.warning(f"[SQLAlchemyDBManager] 初始化传统数据库管理器失败: {e}，部分功能可能不可用")
            logger.info("[SQLAlchemyDBManager] 初始化完成")

    @property
    def db_backend(self):
        """
        提供 db_backend 属性用于向后兼容

        返回传统数据库管理器的 db_backend
        """
        if self._legacy_db:
            return self._legacy_db.db_backend
        return None

    async def start(self) -> bool:
        """
        启动数据库管理器（带并发保护）

        Returns:
            bool: 是否启动成功
        """
        # 使用锁防止并发启动
        async with self._start_lock:
            if self._started:
                logger.debug("[SQLAlchemyDBManager] 已经启动，跳过")
                return True

            if self._starting:
                logger.warning("[SQLAlchemyDBManager] 正在启动中，等待完成...")
                # 等待启动完成
                for _ in range(50):  # 最多等待5秒
                    await asyncio.sleep(0.1)
                    if self._started:
                        return True
                logger.error("[SQLAlchemyDBManager] 启动超时")
                return False

            try:
                self._starting = True
                logger.info("[SQLAlchemyDBManager] 开始启动数据库管理器...")

                # 启动传统数据库管理器（用于委托未实现的方法）
                if self._legacy_db:
                    legacy_started = await self._legacy_db.start()
                    if not legacy_started:
                        logger.warning("[SQLAlchemyDBManager] 传统数据库管理器启动失败，部分功能可能不可用")

                # 获取数据库 URL
                db_url = self._get_database_url()

                # 如果是 MySQL，先确保数据库存在
                if hasattr(self.config, 'db_type') and self.config.db_type.lower() == 'mysql':
                    await self._ensure_mysql_database_exists()

                # 创建数据库引擎
                self.engine = DatabaseEngine(db_url, echo=False)

                logger.info("[SQLAlchemyDBManager] 数据库引擎已创建")
                # 创建表结构（如果不存在）
                await self.engine.create_tables()

                # 健康检查
                if await self.engine.health_check():
                    logger.info("✅ [SQLAlchemyDBManager] 数据库启动成功")
                    self._started = True
                    self._starting = False
                    return True
                else:
                    self._started = False
                    self._starting = False
                    logger.error("❌ [SQLAlchemyDBManager] 数据库健康检查失败")
                    return False

            except Exception as e:
                self._started = False
                self._starting = False
                logger.error(f"❌ [SQLAlchemyDBManager] 启动失败: {e}", exc_info=True)
                return False

    async def stop(self) -> bool:
        """
        停止数据库管理器

        Returns:
            bool: 是否停止成功
        """
        if not self._started:
            return True

        try:
            # ⚠️ 不停止传统数据库管理器，因为 Web UI 路由可能随时需要它
            # 传统数据库会在插件卸载时由 AstrBot 框架自动清理
            # if self._legacy_db:
            #     await self._legacy_db.stop()

            logger.debug("[SQLAlchemyDBManager] 保持传统数据库运行（用于 Web UI 兼容）")

            # 停止 SQLAlchemy 引擎
            if self.engine:
                await self.engine.close()

            self._started = False
            logger.info("✅ [SQLAlchemyDBManager] 数据库已停止（传统数据库保持运行）")
            return True

        except Exception as e:
            logger.error(f"❌ [SQLAlchemyDBManager] 停止失败: {e}")
            return False

    def _get_database_url(self) -> str:
        """
        获取数据库连接 URL

        Returns:
            str: 数据库 URL
        """
        import os

        # 检查数据库类型
        if hasattr(self.config, 'db_type') and self.config.db_type.lower() == 'mysql':
            # MySQL 数据库
            host = getattr(self.config, 'mysql_host', 'localhost')
            port = getattr(self.config, 'mysql_port', 3306)
            user = getattr(self.config, 'mysql_user', 'root')
            password = getattr(self.config, 'mysql_password', '')
            database = getattr(self.config, 'mysql_database', 'astrbot_self_learning')

            return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
        else:
            # SQLite 数据库（默认）
            db_path = getattr(self.config, 'messages_db_path', None)

            if not db_path:
                # 使用默认路径
                db_path = os.path.join(self.config.data_dir, 'messages.db')

            # 确保路径是绝对路径
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)

            return f"sqlite:///{db_path}"

    async def _ensure_mysql_database_exists(self):
        """
        确保 MySQL 数据库存在，如果不存在则创建
        """
        try:
            import aiomysql

            host = getattr(self.config, 'mysql_host', 'localhost')
            port = getattr(self.config, 'mysql_port', 3306)
            user = getattr(self.config, 'mysql_user', 'root')
            password = getattr(self.config, 'mysql_password', '')
            database = getattr(self.config, 'mysql_database', 'astrbot_self_learning')

            # 先连接到 MySQL 服务器（不指定数据库）
            conn = await aiomysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                charset='utf8mb4'
            )

            try:
                async with conn.cursor() as cursor:
                    # 检查数据库是否存在
                    await cursor.execute(
                        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                        (database,)
                    )
                    result = await cursor.fetchone()

                    if not result:
                        # 数据库不存在，创建它
                        logger.info(f"[SQLAlchemyDBManager] 数据库 {database} 不存在，正在创建...")
                        await cursor.execute(
                            f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        )
                        await conn.commit()
                        logger.info(f"✅ [SQLAlchemyDBManager] 数据库 {database} 创建成功")
                    else:
                        logger.debug(f"[SQLAlchemyDBManager] 数据库 {database} 已存在")

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"❌ [SQLAlchemyDBManager] 确保 MySQL 数据库存在失败: {e}")
            raise

    @asynccontextmanager
    async def get_session(self):
        """
        获取数据库会话（上下文管理器）

        改进: 更宽松的状态检查，检查 engine 是否可用而不是严格依赖 _started 标志
        这样可以避免在并发场景下的状态不一致问题

        用法:
            async with db_manager.get_session() as session:
                repo = AffectionRepository(session)
                result = await repo.get_by_id(1)
        """
        # ✅ 改进：检查 engine 是否存在，而不是仅依赖 _started 标志
        # 这样可以处理启动过程中的并发访问
        if not self.engine:
            # 如果正在启动，等待一小段时间
            if self._starting:
                logger.debug("[SQLAlchemyDBManager] 数据库正在启动中，等待engine创建...")
                for _ in range(30):  # 最多等待3秒
                    await asyncio.sleep(0.1)
                    if self.engine:
                        break

                if not self.engine:
                    raise RuntimeError("数据库管理器启动超时，engine未创建")
            else:
                raise RuntimeError("数据库管理器未启动，engine不存在")

        # DatabaseEngine.get_session() 自动适配当前 event loop，
        # 跨线程调用时会创建独立引擎，无需手动处理
        if not self._started:
            logger.debug("[SQLAlchemyDBManager] get_session: _started=False 但 engine 存在，继续执行")

        session = self.engine.get_session()
        try:
            async with session:
                yield session
        finally:
            await session.close()

    # ============================================================
    # 兼容现有 DatabaseManager 接口的方法
    # 这些方法使用 Repository 实现，但保持与旧接口相同
    # ============================================================

    async def get_user_affection(
        self,
        group_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户好感度（兼容接口）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            Optional[Dict]: 好感度数据
        """
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                affection = await repo.get_by_group_and_user(group_id, user_id)

                if affection:
                    return {
                        'group_id': affection.group_id,
                        'user_id': affection.user_id,
                        'affection_level': affection.affection_level,
                        'max_affection': affection.max_affection,
                        'created_at': affection.created_at,
                        'updated_at': affection.updated_at,
                    }
                return None

        except Exception as e:
            logger.error(f"[SQLAlchemyDBManager] 获取好感度失败: {e}")
            return None

    async def update_user_affection(
        self,
        group_id: str,
        user_id: str,
        new_level: int,
        change_reason: str = "",
        bot_mood: str = ""
    ) -> bool:
        """
        更新用户好感度（兼容接口）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            new_level: 新的好感度等级
            change_reason: 变化原因
            bot_mood: 机器人情绪状态

        Returns:
            bool: 是否更新成功
        """
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)

                # 获取当前好感度以计算delta
                current = await repo.get_by_group_and_user(group_id, user_id)
                previous_level = current.affection_level if current else 0
                affection_delta = new_level - previous_level

                # 使用 Repository 的 update_level 方法
                affection = await repo.update_level(
                    group_id,
                    user_id,
                    affection_delta,
                    max_affection=100  # 默认最大值
                )

                # TODO: 如果需要记录 change_reason 和 bot_mood，需要扩展 Repository
                # 当前版本忽略这些参数，保持向后兼容

                return affection is not None

        except Exception as e:
            logger.error(f"[SQLAlchemyDBManager] 更新好感度失败: {e}")
            return False

    async def get_all_user_affections(
        self,
        group_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取群组所有用户好感度（兼容接口）

        Args:
            group_id: 群组 ID

        Returns:
            List[Dict]: 好感度列表
        """
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                affections = await repo.find_many(group_id=group_id)

                return [
                    {
                        'group_id': a.group_id,
                        'user_id': a.user_id,
                        'affection_level': a.affection_level,
                        'max_affection': a.max_affection,
                        'created_at': a.created_at,
                        'updated_at': a.updated_at,
                    }
                    for a in affections
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemyDBManager] 获取所有好感度失败: {e}")
            return []

    async def get_total_affection(self, group_id: str) -> int:
        """
        获取群组总好感度（兼容接口）

        Args:
            group_id: 群组 ID

        Returns:
            int: 总好感度
        """
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                return await repo.get_total_affection(group_id)

        except Exception as e:
            logger.error(f"[SQLAlchemyDBManager] 获取总好感度失败: {e}")
            return 0

    async def save_bot_mood(
        self,
        group_id: str,
        mood_type: str,
        mood_intensity: float,
        mood_description: str,
        duration_hours: int = 24
    ) -> bool:
        """
        保存bot情绪状态（兼容接口）

        注意: 这个方法暂时保持原有实现，因为情绪系统
        还没有对应的ORM模型。后续可以添加BotMood模型。

        Args:
            group_id: 群组 ID
            mood_type: 情绪类型
            mood_intensity: 情绪强度
            mood_description: 情绪描述
            duration_hours: 持续时间（小时）

        Returns:
            bool: 是否保存成功
        """
        # TODO: 等待 BotMood ORM 模型创建后实现
        logger.debug(f"[SQLAlchemyDBManager] save_bot_mood 暂未实现，使用原有实现")
        return True

    # ============================================================
    # Repository 访问方法（新增）
    # 直接返回 Repository 实例，供高级用法使用
    # ============================================================

    def get_affection_repo(self, session) -> AffectionRepository:
        """获取好感度 Repository"""
        return AffectionRepository(session)

    def get_interaction_repo(self, session) -> InteractionRepository:
        """获取互动记录 Repository"""
        return InteractionRepository(session)

    def get_conversation_repo(self, session) -> ConversationHistoryRepository:
        """获取对话历史 Repository"""
        return ConversationHistoryRepository(session)

    def get_diversity_repo(self, session) -> DiversityRepository:
        """获取多样性 Repository"""
        return DiversityRepository(session)

    def get_memory_repo(self, session) -> MemoryRepository:
        """获取记忆 Repository"""
        return MemoryRepository(session)

    def get_psychological_repo(self, session) -> PsychologicalStateRepository:
        """获取心理状态 Repository"""
        return PsychologicalStateRepository(session)

    def get_social_profile_repo(self, session) -> SocialProfileRepository:
        """获取社交档案 Repository"""
        return SocialProfileRepository(session)

    # ============================================================
    # 工具方法
    # ============================================================

    def is_started(self) -> bool:
        """检查是否已启动"""
        return self._started

    async def health_check(self) -> bool:
        """健康检查"""
        if not self.engine:
            return False
        return await self.engine.health_check()

    def get_engine_info(self) -> dict:
        """获取引擎信息"""
        if not self.engine:
            return {}
        return self.engine.get_engine_info()

    # ============================================================
    # 兼容性方法 - 优先使用现代 Repository 实现，失败时降级
    # ============================================================

    async def get_user_social_relations(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取用户社交关系

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现
        """
        try:
            # 尝试使用 Repository 实现
            async with self.get_session() as session:
                from sqlalchemy import select, and_, or_
                from ..models.orm import UserSocialRelationComponent

                # 构建用户标识（支持两种格式）
                user_keys = [user_id, f"{group_id}:{user_id}"]

                # 查询用户发起的关系
                stmt_outgoing = select(UserSocialRelationComponent).where(
                    and_(
                        UserSocialRelationComponent.group_id == group_id,
                        or_(*[UserSocialRelationComponent.from_user_id == key for key in user_keys])  # ✅ 修正字段名
                    )
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.value.desc()  # ✅ 修正字段名 strength → value
                ).limit(self.config.default_social_limit)

                result = await session.execute(stmt_outgoing)
                outgoing_relations = result.scalars().all()

                # 查询指向用户的关系
                stmt_incoming = select(UserSocialRelationComponent).where(
                    and_(
                        UserSocialRelationComponent.group_id == group_id,
                        or_(*[UserSocialRelationComponent.to_user_id == key for key in user_keys])  # ✅ 修正字段名
                    )
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.value.desc()  # ✅ 修正字段名 strength → value
                ).limit(self.config.default_social_limit)

                result = await session.execute(stmt_incoming)
                incoming_relations = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 使用 Repository 查询社交关系: {user_id} in {group_id}")

                return {
                    'user_id': user_id,
                    'group_id': group_id,
                    'outgoing': [
                        {
                            'from_user': r.from_user_id,  # ✅ 修正字段名
                            'to_user': r.to_user_id,      # ✅ 修正字段名
                            'relation_type': r.relation_type,
                            'strength': r.value,           # ✅ 修正字段名 strength → value
                            'frequency': r.frequency,
                            'last_interaction': r.last_interaction  # ✅ 修正字段名
                        }
                        for r in outgoing_relations
                    ],
                    'incoming': [
                        {
                            'from_user': r.from_user_id,  # ✅ 修正字段名
                            'to_user': r.to_user_id,      # ✅ 修正字段名
                            'relation_type': r.relation_type,
                            'strength': r.value,           # ✅ 修正字段名 strength → value
                            'frequency': r.frequency,
                            'last_interaction': r.last_interaction  # ✅ 修正字段名
                        }
                        for r in incoming_relations
                    ],
                    'total_relations': len(outgoing_relations) + len(incoming_relations)
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 查询社交关系失败: {e}")
            raise RuntimeError(f"无法获取用户社交关系: {e}") from e

    async def get_reviewed_persona_learning_updates(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: str = None
    ) -> List[Dict[str, Any]]:
        """
        获取已审查的人格学习更新

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现
        """
        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import PersonaLearningReviewRepository

                repo = PersonaLearningReviewRepository(session)
                reviews = await repo.get_reviewed_updates(limit, offset, status_filter)

                logger.debug(f"[SQLAlchemy] 使用 Repository 查询已审查人格更新: {len(reviews)} 条")

                return [
                    {
                        'id': review.id,
                        'group_id': review.group_id,
                        'timestamp': review.timestamp,
                        'update_type': review.update_type,
                        'original_content': review.original_content,
                        'new_content': review.new_content,
                        'reason': review.reason,
                        'confidence': review.confidence_score,
                        'status': review.status,
                        'reviewer_comment': review.reviewer_comment,
                        'review_time': review.review_time
                    }
                    for review in reviews
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 查询已审查人格更新失败: {e}")
            raise RuntimeError(f"无法获取已审查人格更新: {e}") from e

    async def get_trends_data(self) -> Dict[str, Any]:
        """
        获取趋势数据

        使用 SQLAlchemy Repository 实现，支持跨线程调用（NullPool），基于现有数据计算趋势
        """
        try:
            # 尝试使用 Repository 计算趋势
            async with self.get_session() as session:
                from sqlalchemy import select, func, cast, Date
                from ..models.orm import UserAffection, InteractionRecord
                from datetime import datetime, timedelta

                # 计算趋势的天数范围（使用配置中的 trend_analysis_days）
                days_ago = int((datetime.now() - timedelta(days=self.config.trend_analysis_days)).timestamp())

                # 根据数据库类型选择日期转换函数
                is_mysql = self.config.db_type.lower() == 'mysql'

                if is_mysql:
                    # MySQL: 使用 FROM_UNIXTIME 和 DATE
                    date_func_affection = func.date(func.from_unixtime(UserAffection.updated_at))
                    date_func_interaction = func.date(func.from_unixtime(InteractionRecord.timestamp))
                else:
                    # SQLite: 使用 datetime(timestamp, 'unixepoch') 和 date()
                    date_func_affection = func.date(UserAffection.updated_at, 'unixepoch')
                    date_func_interaction = func.date(InteractionRecord.timestamp, 'unixepoch')

                # 好感度趋势（按天统计）
                affection_stmt = select(
                    date_func_affection.label('date'),
                    func.avg(UserAffection.affection_level).label('avg_affection'),
                    func.count(UserAffection.id).label('count')
                ).where(
                    UserAffection.updated_at >= days_ago
                ).group_by(
                    date_func_affection
                ).order_by('date')

                affection_result = await session.execute(affection_stmt)
                affection_trend = [
                    {
                        'date': str(row.date),
                        'avg_affection': float(row.avg_affection) if row.avg_affection else 0.0,
                        'count': row.count
                    }
                    for row in affection_result
                ]

                # 互动趋势（按天统计）
                interaction_stmt = select(
                    date_func_interaction.label('date'),
                    func.count(InteractionRecord.id).label('count')
                ).where(
                    InteractionRecord.timestamp >= days_ago
                ).group_by(
                    date_func_interaction
                ).order_by('date')

                interaction_result = await session.execute(interaction_stmt)
                interaction_trend = [
                    {
                        'date': str(row.date),
                        'count': row.count
                    }
                    for row in interaction_result
                ]

                logger.debug("[SQLAlchemy] 使用 Repository 计算趋势数据")

                return {
                    "affection_trend": affection_trend,
                    "interaction_trend": interaction_trend,
                    "learning_trend": []  # 学习趋势需要学习记录表
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 计算趋势数据失败: {e}")
            raise RuntimeError(f"无法获取趋势数据: {e}") from e

    async def get_style_learning_statistics(self) -> Dict[str, Any]:
        """
        获取风格学习统计

        使用 SQLAlchemy Repository 实现，支持跨线程调用（NullPool）
        """
        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import StyleLearningReviewRepository

                repo = StyleLearningReviewRepository(session)
                statistics = await repo.get_statistics()

                logger.debug("[SQLAlchemy] 使用 Repository 计算风格学习统计")

                return statistics

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取风格学习统计失败: {e}")
            raise RuntimeError(f"无法获取风格学习统计: {e}") from e

    async def get_pending_persona_learning_reviews(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取待审查的人格学习更新

        使用 SQLAlchemy Repository 实现，支持跨线程调用（NullPool）

        Args:
            limit: 最大返回数量（None则使用配置中的default_review_limit）
        """
        if limit is None:
            limit = self.config.default_review_limit

        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import PersonaLearningReviewRepository

                repo = PersonaLearningReviewRepository(session)
                reviews = await repo.get_pending_reviews(limit)

                logger.debug(f"[SQLAlchemy] 使用 Repository 查询待审查人格更新: {len(reviews)} 条")

                # 解析 metadata JSON 字符串
                import json
                result = []
                for review in reviews:
                    # 解析 metadata 字段（如果是字符串）
                    metadata = review.metadata_
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata) if metadata else {}
                        except json.JSONDecodeError:
                            metadata = {}
                    elif metadata is None:
                        metadata = {}

                    result.append({
                        'id': review.id,
                        'group_id': review.group_id,
                        'timestamp': review.timestamp,
                        'update_type': review.update_type,
                        'original_content': review.original_content,
                        'new_content': review.new_content,
                        'proposed_content': review.proposed_content,
                        'confidence_score': review.confidence_score,
                        'reason': review.reason,
                        'status': review.status,
                        'reviewer_comment': review.reviewer_comment,
                        'review_time': review.review_time,
                        'metadata': metadata  # 已解析为字典
                    })

                return result

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 查询待审查人格更新失败: {e}")
            raise RuntimeError(f"无法获取待审查人格更新: {e}") from e

    async def get_pending_style_reviews(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取待审查的风格学习更新

        使用 SQLAlchemy Repository 实现，支持跨线程调用（NullPool）

        Args:
            limit: 最大返回数量（None则使用配置中的default_review_limit）
        """
        if limit is None:
            limit = self.config.default_review_limit

        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import StyleLearningReviewRepository

                repo = StyleLearningReviewRepository(session)
                reviews = await repo.get_pending_reviews(limit)

                logger.debug(f"[SQLAlchemy] 使用 Repository 查询待审查风格更新: {len(reviews)} 条")

                return [
                    {
                        'id': review.id,
                        'type': review.type,  # 使用 type 而不是 pattern_type
                        'group_id': review.group_id,
                        'timestamp': review.timestamp,
                        'learned_patterns': review.learned_patterns,  # JSON格式
                        'few_shots_content': review.few_shots_content,
                        'status': review.status,
                        'description': review.description,
                        'created_at': review.created_at
                    }
                    for review in reviews
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 查询待审查风格更新失败: {e}")
            raise RuntimeError(f"无法获取待审查风格更新: {e}") from e

    async def get_reviewed_style_learning_updates(
        self,
        limit: int = None,
        offset: int = 0,
        status_filter: str = None
    ) -> List[Dict[str, Any]]:
        """
        获取已审查的风格学习更新

        使用 SQLAlchemy Repository 实现，支持跨线程调用（NullPool）

        Args:
            limit: 最大返回数量（None则使用配置中的default_review_limit）
            offset: 偏移量
            status_filter: 状态过滤（'approved', 'rejected', None表示全部）

        Returns:
            List[Dict]: 已审查的风格学习记录列表
        """
        if limit is None:
            limit = self.config.default_review_limit

        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm.learning import StyleLearningReview

                # 构建查询
                stmt = select(StyleLearningReview)

                # 状态过滤
                if status_filter:
                    stmt = stmt.where(StyleLearningReview.status == status_filter)
                else:
                    # 只查询非 pending 状态的记录
                    stmt = stmt.where(StyleLearningReview.status != 'pending')

                # 按时间倒序排列
                stmt = stmt.order_by(StyleLearningReview.review_time.desc())

                # 分页
                stmt = stmt.offset(offset).limit(limit)

                result = await session.execute(stmt)
                reviews = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询已审查风格更新: {len(reviews)} 条 (状态={status_filter})")

                return [
                    {
                        'id': review.id,
                        'type': review.type,
                        'group_id': review.group_id,
                        'timestamp': review.timestamp,
                        'learned_patterns': review.learned_patterns,
                        'few_shots_content': review.few_shots_content,
                        'status': review.status,
                        'description': review.description,
                        'reviewer_comment': review.reviewer_comment,
                        'review_time': review.review_time,
                        'created_at': review.created_at
                    }
                    for review in reviews
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询已审查风格更新失败: {e}")
            raise RuntimeError(f"无法获取已审查风格更新: {e}") from e

    async def update_style_review_status(
        self,
        review_id: int,
        status: str,
        reviewer_comment: str = None
    ) -> bool:
        """
        更新风格审查状态

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现
        """
        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import StyleLearningReviewRepository

                repo = StyleLearningReviewRepository(session)
                success = await repo.update_review_status(review_id, status, reviewer_comment)

                if success:
                    logger.debug(f"[SQLAlchemy] 使用 Repository 更新风格审查状态: {review_id} -> {status}")

                return success

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 更新风格审查状态失败: {e}")
            raise RuntimeError(f"无法更新风格审查状态: {e}") from e

    async def delete_persona_learning_review_by_id(self, review_id: int) -> bool:
        """
        删除人格学习审查记录

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现
        """
        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import PersonaLearningReviewRepository

                repo = PersonaLearningReviewRepository(session)
                success = await repo.delete_by_id(review_id)

                if success:
                    logger.debug(f"[SQLAlchemy] 使用 Repository 删除人格学习审查: {review_id}")

                return success

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 删除人格学习审查失败: {e}")
            raise RuntimeError(f"无法删除人格学习审查: {e}") from e

    async def add_persona_learning_review(
        self,
        group_id: str,
        proposed_content: str,
        learning_source: str = "expression_learning",
        confidence_score: float = 0.5,
        raw_analysis: str = "",
        metadata: Dict[str, Any] = None,
        original_content: str = "",
        new_content: str = ""
    ) -> int:
        """
        添加人格学习审查记录

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            group_id: 群组ID
            proposed_content: 建议的增量人格内容
            learning_source: 学习来源
            confidence_score: 置信度分数
            raw_analysis: 原始分析结果
            metadata: 元数据
            original_content: 原人格完整文本
            new_content: 新人格完整文本

        Returns:
            int: 插入记录的ID
        """
        try:
            async with self.get_session() as session:
                from ..models.orm.learning import PersonaLearningReview
                import time
                import json

                # 创建记录
                review = PersonaLearningReview(
                    group_id=group_id,
                    timestamp=time.time(),  # ✅ 使用 Float 类型（与 ORM 模型定义一致）
                    update_type=learning_source,
                    original_content=original_content,
                    new_content=new_content,
                    proposed_content=proposed_content,
                    confidence_score=confidence_score,
                    reason=raw_analysis,
                    status='pending',
                    reviewer_comment=None,
                    review_time=None,
                    metadata_=json.dumps(metadata) if metadata else None,
                    # ❌ 移除 created_at - PersonaLearningReview 模型没有此字段
                )

                session.add(review)
                await session.commit()
                await session.refresh(review)

                logger.debug(f"[SQLAlchemy] 已添加人格学习审查记录: ID={review.id}, group={group_id}")
                return review.id

        except Exception as e:
            logger.error(f"[SQLAlchemy] 添加人格学习审查记录失败: {e}", exc_info=True)
            raise RuntimeError(f"无法添加人格学习审查记录: {e}") from e

    async def get_messages_statistics(self) -> Dict[str, Any]:
        """
        获取消息统计信息

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）
        统计 raw_messages 和 filtered_messages 表的数据

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import RawMessage, FilteredMessage

                # 统计原始消息数量
                total_stmt = select(func.count()).select_from(RawMessage)
                total_result = await session.execute(total_stmt)
                total_messages = total_result.scalar() or 0

                # 统计筛选后消息数量
                filtered_stmt = select(func.count()).select_from(FilteredMessage)
                filtered_result = await session.execute(filtered_stmt)
                filtered_messages = filtered_result.scalar() or 0

                # 计算筛选率
                filter_rate = (filtered_messages / total_messages * 100) if total_messages > 0 else 0.0

                return {
                    "total_messages": total_messages,
                    "filtered_messages": filtered_messages,
                    "filter_rate": round(filter_rate, 2)
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取消息统计失败: {e}")
            raise RuntimeError(f"无法获取消息统计: {e}") from e

    async def get_all_expression_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有群组的表达模式

        使用 SQLAlchemy Repository 实现，支持跨线程调用

        Returns:
            Dict[str, List[Dict[str, Any]]]: 群组ID -> 表达模式列表的映射
        """
        try:
            # 直接使用 ORM，引擎已配置支持多线程
            # SQLite: check_same_thread=False
            # MySQL: NullPool 每次都创建新连接
            async with self.get_session() as session:
                from ..repositories.expression_repository import ExpressionPatternRepository

                repo = ExpressionPatternRepository(session)
                patterns_by_group = await repo.get_all_patterns()

                logger.debug(f"[SQLAlchemy] 使用 Repository 获取所有表达模式: {len(patterns_by_group)} 个群组")

                # 转换为 WebUI 所需的字典格式
                result = {}
                for group_id, patterns in patterns_by_group.items():
                    result[group_id] = [
                        {
                            'situation': pattern.situation,
                            'expression': pattern.expression,
                            'weight': pattern.weight,
                            'last_active_time': pattern.last_active_time,
                            'created_time': pattern.create_time,
                            'group_id': pattern.group_id,
                            'style_type': 'general'  # 兼容字段
                        }
                        for pattern in patterns
                    ]

                return result

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 获取表达模式失败: {e}")
            raise RuntimeError(f"无法获取表达模式: {e}") from e

    async def get_expression_patterns_statistics(self) -> Dict[str, Any]:
        """
        获取表达模式统计信息

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            async with self.get_session() as session:
                from ..repositories.expression_repository import ExpressionPatternRepository

                repo = ExpressionPatternRepository(session)
                stats = await repo.get_statistics()

                logger.debug(f"[SQLAlchemy] 使用 Repository 获取表达模式统计: {stats}")

                return stats

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 获取表达模式统计失败: {e}")
            raise RuntimeError(f"无法获取表达模式统计: {e}") from e

    async def get_group_expression_patterns(self, group_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取指定群组的表达模式

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现

        Args:
            group_id: 群组ID
            limit: 最大返回数量（None则使用配置中的default_pattern_limit）

        Returns:
            List[Dict[str, Any]]: 表达模式列表（按权重降序）
        """
        if limit is None:
            limit = self.config.default_pattern_limit

        try:
            async with self.get_session() as session:
                from ..repositories.expression_repository import ExpressionPatternRepository

                repo = ExpressionPatternRepository(session)
                patterns = await repo.get_patterns_by_group(group_id, limit)

                logger.debug(f"[SQLAlchemy] 使用 Repository 获取群组 {group_id} 的表达模式: {len(patterns)} 条")

                return [
                    {
                        'situation': pattern.situation,
                        'expression': pattern.expression,
                        'weight': pattern.weight,
                        'last_active_time': pattern.last_active_time,
                        'created_time': pattern.create_time,
                        'group_id': pattern.group_id,
                        'style_type': 'general'  # 兼容字段
                    }
                    for pattern in patterns
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] Repository 获取群组表达模式失败: {e}")
            raise RuntimeError(f"无法获取群组表达模式: {e}") from e

    # ========================================
    # 社交关系系统方法（使用新ORM表）
    # ========================================

    async def get_social_relations_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """
        获取指定群组的社交关系（使用新ORM表）

        Args:
            group_id: 群组ID

        Returns:
            List[Dict[str, Any]]: 社交关系列表
        """
        try:
            async with self.get_session() as session:
                # 使用新的 user_social_relation_components 表
                from sqlalchemy import select
                from ..models.orm.social_relation import UserSocialRelationComponent

                # 查询该群组的所有社交关系组件
                stmt = select(UserSocialRelationComponent).where(
                    UserSocialRelationComponent.group_id == group_id
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.value.desc()
                )

                result = await session.execute(stmt)
                components = result.scalars().all()

                # 转换为旧格式的字典（保持向后兼容）
                relations = []
                for comp in components:
                    relations.append({
                        'from_user': f"{comp.group_id}:{comp.from_user_id}",  # 兼容旧格式
                        'to_user': f"{comp.group_id}:{comp.to_user_id}",
                        'relation_type': comp.relation_type,
                        'strength': float(comp.value),  # value 对应 strength
                        'frequency': int(comp.frequency),
                        'last_interaction': comp.last_interaction
                    })

                logger.info(f"[SQLAlchemy] 群组 {group_id} 加载了 {len(relations)} 条社交关系")
                return relations

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取社交关系失败: {e}", exc_info=True)
            return []

    async def load_social_graph(self, group_id: str) -> List[Dict[str, Any]]:
        """
        加载社交图谱（使用新ORM表）

        Args:
            group_id: 群组ID

        Returns:
            List[Dict[str, Any]]: 社交关系列表
        """
        # load_social_graph 与 get_social_relations_by_group 功能相同
        return await self.get_social_relations_by_group(group_id)

    async def get_user_social_relations(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取指定用户在群组中的社交关系（使用新ORM表）

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            Dict: 包含用户社交关系的字典
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, or_
                from ..models.orm.social_relation import UserSocialRelationComponent

                # 查询该用户发起或接收的所有关系
                stmt = select(UserSocialRelationComponent).where(
                    UserSocialRelationComponent.group_id == group_id
                ).where(
                    or_(
                        UserSocialRelationComponent.from_user_id == user_id,
                        UserSocialRelationComponent.to_user_id == user_id
                    )
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.value.desc()
                ).limit(10)

                result = await session.execute(stmt)
                components = result.scalars().all()

                # 分类为发起关系和接收关系
                outgoing_relations = []
                incoming_relations = []

                for comp in components:
                    relation_dict = {
                        'from_user': f"{comp.group_id}:{comp.from_user_id}",
                        'to_user': f"{comp.group_id}:{comp.to_user_id}",
                        'relation_type': comp.relation_type,
                        'strength': float(comp.value),
                        'frequency': int(comp.frequency),
                        'last_interaction': comp.last_interaction
                    }

                    if comp.from_user_id == user_id:
                        outgoing_relations.append(relation_dict)
                    else:
                        incoming_relations.append(relation_dict)

                return {
                    'outgoing': outgoing_relations,
                    'incoming': incoming_relations,
                    'total_relations': len(components)
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取用户社交关系失败: {e}", exc_info=True)
            return {'outgoing': [], 'incoming': [], 'total_relations': 0}

    async def save_social_relation(self, group_id: str, relation_data: Dict[str, Any]):
        """
        保存社交关系（使用新ORM表）

        Args:
            group_id: 群组ID
            relation_data: 关系数据
        """
        try:
            async with self.get_session() as session:
                from ..models.orm.social_relation import UserSocialRelationComponent, UserSocialProfile
                from sqlalchemy import select
                import time
                from datetime import datetime

                # 解析 from_user 和 to_user（兼容旧格式 "group_id:user_id"）
                from_user = relation_data.get('from_user', '')
                to_user = relation_data.get('to_user', '')

                # 提取用户ID（如果包含 group_id:）
                from_user_id = from_user.split(':')[-1] if ':' in from_user else from_user
                to_user_id = to_user.split(':')[-1] if ':' in to_user else to_user

                # 处理 last_interaction 时间戳（支持 ISO 格式字符串和数值）
                last_interaction_raw = relation_data.get('last_interaction', time.time())
                if isinstance(last_interaction_raw, str):
                    # ISO 格式字符串 -> Unix 时间戳
                    try:
                        dt = datetime.fromisoformat(last_interaction_raw.replace('Z', '+00:00'))
                        last_interaction = int(dt.timestamp())
                    except (ValueError, AttributeError):
                        last_interaction = int(time.time())
                elif isinstance(last_interaction_raw, (int, float)):
                    last_interaction = int(last_interaction_raw)
                else:
                    last_interaction = int(time.time())

                # 获取或创建 from_user 的社交档案
                stmt = select(UserSocialProfile).where(
                    UserSocialProfile.user_id == from_user_id,
                    UserSocialProfile.group_id == group_id
                )
                result = await session.execute(stmt)
                profile = result.scalars().first()

                if not profile:
                    # 创建新的用户社交档案
                    profile = UserSocialProfile(
                        user_id=from_user_id,
                        group_id=group_id,
                        total_relations=0,
                        significant_relations=0,
                        created_at=int(time.time()),
                        last_updated=int(time.time())
                    )
                    session.add(profile)
                    await session.flush()  # 确保获得 profile.id

                # 创建新的社交关系组件
                component = UserSocialRelationComponent(
                    profile_id=profile.id,
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    group_id=group_id,
                    relation_type=relation_data.get('relation_type', 'unknown'),
                    value=float(relation_data.get('strength', 0.0)),
                    frequency=int(relation_data.get('frequency', 0)),
                    last_interaction=last_interaction,
                    created_at=int(time.time())
                )

                session.add(component)

                # 更新用户档案统计信息
                profile.total_relations += 1
                profile.last_updated = int(time.time())

                await session.commit()

                logger.debug(f"[SQLAlchemy] 已保存社交关系: {from_user_id} -> {to_user_id}")

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存社交关系失败: {e}", exc_info=True)

    # ========================================
    # 其他必要方法
    # ========================================

    def get_db_connection(self):
        """
        获取数据库连接（上下文管理器）

        用于向后兼容传统代码
        返回一个模拟传统数据库连接的适配器

        Returns:
            AsyncContextManager: 异步上下文管理器
        """
        @asynccontextmanager
        async def _connection_context():
            # 检查数据库管理器是否已启动
            if not self._started or not self.engine:
                raise RuntimeError(
                    "[SQLAlchemy] 数据库引擎未初始化。请确保已调用 start() 方法。"
                    f"状态: _started={self._started}, engine={'已创建' if self.engine else '未创建'}"
                )

            # 创建一个兼容传统接口的连接适配器
            class SQLAlchemyConnectionAdapter:
                """SQLAlchemy 连接适配器 - 模拟传统数据库连接接口"""
                def __init__(self, session_factory):
                    self.session_factory = session_factory
                    self._session = None

                async def cursor(self):
                    """返回游标适配器"""
                    if not self._session:
                        self._session = self.session_factory()
                    return SQLAlchemyCursorAdapter(self._session)

                async def commit(self):
                    """提交事务"""
                    if self._session:
                        await self._session.commit()

                async def rollback(self):
                    """回滚事务"""
                    if self._session:
                        await self._session.rollback()

                async def close(self):
                    """关闭会话"""
                    if self._session:
                        await self._session.close()

            class SQLAlchemyCursorAdapter:
                """SQLAlchemy 游标适配器"""
                def __init__(self, session):
                    self.session = session
                    self._result = None
                    self.lastrowid = None
                    self.rowcount = 0

                async def execute(self, sql, params=None):
                    """执行 SQL 语句"""
                    from sqlalchemy import text
                    from sqlalchemy import inspect

                    # 检测并转换 SQLite 专用查询
                    sql_converted = self._convert_sqlite_queries(sql)

                    # 转换参数格式（? → :1, :2...）
                    if params:
                        # 将 ? 占位符转换为命名参数
                        param_dict = {}
                        if isinstance(params, (list, tuple)):
                            for i, param in enumerate(params):
                                param_name = f"param_{i}"
                                sql_converted = sql_converted.replace('?', f":{param_name}", 1)
                                param_dict[param_name] = param
                            self._result = await self.session.execute(text(sql_converted), param_dict)
                        else:
                            self._result = await self.session.execute(text(sql_converted), params)
                    else:
                        self._result = await self.session.execute(text(sql_converted))

                    self.rowcount = self._result.rowcount if hasattr(self._result, 'rowcount') else 0
                    return self

                def _convert_sqlite_queries(self, sql: str) -> str:
                    """
                    转换 SQLite 专用查询为数据库无关查询

                    Args:
                        sql: 原始 SQL 查询

                    Returns:
                        str: 转换后的 SQL 查询
                    """
                    import re

                    # 检测数据库类型
                    dialect_name = self.session.bind.dialect.name if self.session.bind else 'sqlite'

                    # 如果是 SQLite，不需要转换
                    if dialect_name == 'sqlite':
                        return sql

                    # MySQL: 转换 sqlite_master 查询
                    if 'sqlite_master' in sql.lower():
                        if dialect_name == 'mysql':
                            # 提取表名检查模式
                            # 匹配: SELECT name FROM sqlite_master WHERE type='table' AND name='表名'
                            pattern = r"SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*['\"]table['\"]\s+AND\s+name\s*=\s*['\"](\w+)['\"]"
                            match = re.search(pattern, sql, re.IGNORECASE)

                            if match:
                                table_name = match.group(1)
                                # MySQL: 查询 INFORMATION_SCHEMA
                                converted = f"""
                                    SELECT TABLE_NAME as name
                                    FROM INFORMATION_SCHEMA.TABLES
                                    WHERE TABLE_SCHEMA = DATABASE()
                                    AND TABLE_NAME = '{table_name}'
                                """
                                logger.debug(f"[SQLAlchemy] 转换 SQLite 查询为 MySQL 查询: {table_name}")
                                return converted.strip()

                            # 匹配: SELECT name FROM sqlite_master WHERE type='table'
                            pattern2 = r"SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*['\"]table['\"]"
                            if re.search(pattern2, sql, re.IGNORECASE):
                                # 列出所有表
                                converted = """
                                    SELECT TABLE_NAME as name
                                    FROM INFORMATION_SCHEMA.TABLES
                                    WHERE TABLE_SCHEMA = DATABASE()
                                """
                                logger.debug("[SQLAlchemy] 转换 SQLite 查询为 MySQL 查询: 列出所有表")
                                return converted.strip()

                    return sql

                async def fetchone(self):
                    """获取一行"""
                    if self._result:
                        return self._result.fetchone()
                    return None

                async def fetchall(self):
                    """获取所有行"""
                    if self._result:
                        return self._result.fetchall()
                    return []

                async def close(self):
                    """关闭游标"""
                    if self._result:
                        self._result.close()

            # 创建并返回连接适配器
            adapter = SQLAlchemyConnectionAdapter(self.engine.get_session)
            try:
                yield adapter
            finally:
                await adapter.close()

        return _connection_context()

    async def get_group_connection(self, group_id: str):
        """
        获取群组数据库连接（用于向后兼容）

        注意：此方法已废弃，新代码应使用 get_session()
        为了向后兼容，返回 get_db_connection() 的结果

        Args:
            group_id: 群组ID

        Returns:
            Connection: 数据库连接适配器
        """
        # 返回通用连接（不区分群组）
        return self.get_db_connection()

    async def mark_messages_processed(self, message_ids: List[int]):
        """
        标记消息为已处理

        注意：UserConversationHistory ORM 模型暂无 processed 字段
        此方法暂时不执行实际操作，仅记录日志

        Args:
            message_ids: 消息ID列表
        """
        if not message_ids:
            return

        try:
            # TODO: 为 UserConversationHistory 添加 processed 字段后实现
            logger.debug(f"[SQLAlchemy] mark_messages_processed 调用（暂不实现）: {len(message_ids)} 条消息")

        except Exception as e:
            logger.error(f"[SQLAlchemy] 标记消息处理状态失败: {e}", exc_info=True)

    async def save_learning_performance_record(self, group_id: str, performance_data: Dict[str, Any]) -> bool:
        """
        保存学习性能记录

        Args:
            group_id: 群组ID
            performance_data: 性能记录数据

        Returns:
            bool: 是否保存成功
        """
        try:
            async with self.get_session() as session:
                from ..models.orm import LearningPerformanceHistory
                import time

                # 创建学习性能记录
                record = LearningPerformanceHistory(
                    group_id=group_id,
                    session_id=performance_data.get('session_id', ''),
                    timestamp=int(performance_data.get('timestamp', time.time())),
                    quality_score=float(performance_data.get('quality_score', 0.0)),
                    learning_time=float(performance_data.get('learning_time', 0.0)),
                    success=bool(performance_data.get('success', False)),
                    successful_pattern=performance_data.get('successful_pattern', ''),
                    failed_pattern=performance_data.get('failed_pattern', ''),
                    created_at=int(time.time())
                )

                session.add(record)
                await session.commit()

                logger.debug(f"[SQLAlchemy] 已保存学习性能记录: {group_id}")
                return True

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存学习性能记录失败: {e}", exc_info=True)
            return False

    async def get_group_messages_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取群组消息统计

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）
        使用 RawMessage 表进行统计

        Args:
            group_id: 群组ID

        Returns:
            Dict: 消息统计数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import RawMessage

                # 统计总消息数
                total_stmt = select(func.count()).select_from(RawMessage).where(
                    RawMessage.group_id == group_id
                )
                total_result = await session.execute(total_stmt)
                total_messages = total_result.scalar() or 0

                # 统计已处理消息数
                processed_stmt = select(func.count()).select_from(RawMessage).where(
                    RawMessage.group_id == group_id,
                    RawMessage.processed == True
                )
                processed_result = await session.execute(processed_stmt)
                processed_messages = processed_result.scalar() or 0

                # 计算未处理消息数
                unprocessed_messages = total_messages - processed_messages

                return {
                    'total_messages': total_messages,
                    'unprocessed_messages': unprocessed_messages,
                    'processed_messages': processed_messages
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取群组消息统计失败: {e}", exc_info=True)
            raise RuntimeError(f"无法获取群组 {group_id} 的消息统计: {e}") from e

    async def get_jargon_statistics(self, group_id: str = None) -> Dict[str, Any]:
        """
        获取俚语统计信息

        Args:
            group_id: 群组ID（可选，None表示全局统计）

        Returns:
            Dict: 俚语统计数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm.expression import ExpressionPattern

                # 构建查询
                if group_id:
                    stmt = select(func.count()).select_from(ExpressionPattern).where(
                        ExpressionPattern.group_id == group_id
                    )
                else:
                    stmt = select(func.count()).select_from(ExpressionPattern)

                result = await session.execute(stmt)
                total_count = result.scalar() or 0

                return {
                    'total_jargons': total_count,
                    'group_id': group_id
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取俚语统计失败: {e}", exc_info=True)
            return {'total_jargons': 0, 'group_id': group_id}

    async def get_recent_jargon_list(
        self,
        group_id: str = None,
        chat_id: str = None,
        limit: int = 10,
        only_confirmed: bool = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的黑话列表

        Args:
            group_id: 群组ID（可选，None 表示获取所有群组）
            chat_id: 聊天ID（可选，兼容参数）
            limit: 返回数量限制
            only_confirmed: 是否只返回已确认的黑话

        Returns:
            List[Dict]: 黑话列表，包含 content, meaning 等字段
        """
        # chat_id 是 group_id 的别名（向后兼容）
        if group_id is None and chat_id is not None:
            group_id = chat_id

        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import Jargon

                # 构建查询
                stmt = select(Jargon)

                # 如果指定了 group_id，则只查询该群组
                if group_id is not None:
                    stmt = stmt.where(Jargon.chat_id == group_id)

                # 如果只返回已确认的黑话
                if only_confirmed:
                    stmt = stmt.where(Jargon.is_jargon == True)

                # 按更新时间倒序排列，限制数量
                stmt = stmt.order_by(Jargon.updated_at.desc()).limit(limit)

                result = await session.execute(stmt)
                jargon_records = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询最近黑话列表: group_id={group_id}, 数量={len(jargon_records)}")

                jargon_list = []
                for record in jargon_records:
                    try:
                        jargon_list.append({
                            'id': record.id,
                            'content': record.content,
                            'meaning': record.meaning,
                            'is_jargon': record.is_jargon,
                            'count': record.count or 0,
                            'last_inference_count': record.last_inference_count or 0,
                            'is_complete': record.is_complete,
                            'chat_id': record.chat_id,
                            'updated_at': record.updated_at,
                            'is_global': record.is_global or False
                        })
                    except Exception as row_error:
                        logger.warning(f"处理黑话记录行时出错，跳过: {row_error}")
                        continue

                return jargon_list

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取最近黑话列表失败: {e}", exc_info=True)
            return []

    async def get_learning_patterns_data(self, group_id: str = None) -> Dict[str, Any]:
        """
        获取学习模式数据

        Args:
            group_id: 群组ID（可选）

        Returns:
            Dict: 学习模式数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..repositories.learning_repository import PersonaLearningReviewRepository, StyleLearningReviewRepository

                persona_repo = PersonaLearningReviewRepository(session)
                style_repo = StyleLearningReviewRepository(session)

                # 获取人格学习统计
                persona_stats = await persona_repo.get_statistics()

                # 获取风格学习统计
                style_stats = await style_repo.get_statistics()

                return {
                    'persona_learning': persona_stats,
                    'style_learning': style_stats,
                    'group_id': group_id
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取学习模式数据失败: {e}", exc_info=True)
            return {'persona_learning': {}, 'style_learning': {}, 'group_id': group_id}

    async def save_learning_session_record(self, group_id: str, session_data: Dict[str, Any]) -> bool:
        """
        保存学习会话记录

        Args:
            group_id: 群组ID
            session_data: 会话数据

        Returns:
            bool: 是否保存成功
        """
        try:
            # 此方法在新架构中可能不需要，暂时只记录日志
            logger.debug(f"[SQLAlchemy] 学习会话记录（暂不实现）: group={group_id}, data={session_data}")
            return True

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存学习会话记录失败: {e}", exc_info=True)
            return False

    async def get_detailed_metrics(self, group_id: str = None) -> Dict[str, Any]:
        """
        获取详细指标数据

        Args:
            group_id: 群组ID（可选）

        Returns:
            Dict: 详细指标数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import UserAffection, UserConversationHistory, ExpressionPattern

                metrics = {}

                # 好感度指标
                if group_id:
                    affection_stmt = select(
                        func.count(UserAffection.id).label('count'),
                        func.avg(UserAffection.affection_level).label('avg_level')
                    ).where(UserAffection.group_id == group_id)
                else:
                    affection_stmt = select(
                        func.count(UserAffection.id).label('count'),
                        func.avg(UserAffection.affection_level).label('avg_level')
                    )

                affection_result = await session.execute(affection_stmt)
                affection_row = affection_result.first()

                metrics['affection'] = {
                    'total_users': affection_row.count if affection_row else 0,
                    'avg_level': float(affection_row.avg_level) if affection_row and affection_row.avg_level else 0.0
                }

                # 对话历史指标
                if group_id:
                    conv_stmt = select(func.count(UserConversationHistory.id)).where(
                        UserConversationHistory.group_id == group_id
                    )
                else:
                    conv_stmt = select(func.count(UserConversationHistory.id))

                conv_result = await session.execute(conv_stmt)
                conv_count = conv_result.scalar() or 0

                metrics['conversations'] = {
                    'total_count': conv_count
                }

                # 表达模式指标
                if group_id:
                    expr_stmt = select(func.count(ExpressionPattern.id)).where(
                        ExpressionPattern.group_id == group_id
                    )
                else:
                    expr_stmt = select(func.count(ExpressionPattern.id))

                expr_result = await session.execute(expr_stmt)
                expr_count = expr_result.scalar() or 0

                metrics['expressions'] = {
                    'total_patterns': expr_count
                }

                return metrics

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取详细指标失败: {e}", exc_info=True)
            return {'affection': {}, 'conversations': {}, 'expressions': {}}

    async def get_style_progress_data(self, group_id: str = None) -> Dict[str, Any]:
        """
        获取风格进度数据

        Args:
            group_id: 群组ID（可选）

        Returns:
            Dict: 风格进度数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..repositories.learning_repository import StyleLearningReviewRepository

                repo = StyleLearningReviewRepository(session)

                # 获取审核状态统计
                stats = await repo.get_statistics()

                return {
                    'total_reviews': stats.get('total', 0),
                    'approved': stats.get('approved', 0),
                    'rejected': stats.get('rejected', 0),
                    'pending': stats.get('pending', 0),
                    'group_id': group_id
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取风格进度数据失败: {e}", exc_info=True)
            return {'total_reviews': 0, 'approved': 0, 'rejected': 0, 'pending': 0, 'group_id': group_id}

    async def save_raw_message(self, message_data) -> int:
        """
        保存原始消息（纯 ORM 实现）

        Args:
            message_data: 消息数据（对象或字典）

        Returns:
            int: 消息ID
        """
        try:
            async with self.get_session() as session:
                from ..models.orm import RawMessage
                import time

                # 兼容对象和字典两种输入
                if hasattr(message_data, '__dict__'):
                    data = message_data.__dict__
                else:
                    data = message_data

                # 创建原始消息记录
                raw_msg = RawMessage(
                    sender_id=str(data.get('sender_id', '')),
                    sender_name=data.get('sender_name', ''),
                    message=data.get('message', ''),
                    group_id=data.get('group_id', ''),
                    timestamp=int(data.get('timestamp', time.time())),
                    platform=data.get('platform', ''),
                    message_id=data.get('message_id'),
                    reply_to=data.get('reply_to'),
                    created_at=int(time.time()),
                    processed=False
                )

                session.add(raw_msg)
                await session.commit()
                await session.refresh(raw_msg)

                logger.debug(f"[SQLAlchemy] 已保存原始消息: ID={raw_msg.id}, group={data.get('group_id')}")
                return raw_msg.id

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存���始消息失败: {e}", exc_info=True)
            return 0

    async def get_recent_raw_messages(self, group_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """
        获取最近的原始消息

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            group_id: 群组ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 原始消息列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import RawMessage

                # 构建查询：按时间倒序
                stmt = select(RawMessage).where(
                    RawMessage.group_id == group_id
                ).order_by(
                    RawMessage.timestamp.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                messages = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询最近原始消息: 群组={group_id}, 数量={len(messages)}")

                return [
                    {
                        'id': msg.id,
                        'sender_id': msg.sender_id,
                        'sender_name': msg.sender_name,
                        'message': msg.message,
                        'group_id': msg.group_id,
                        'timestamp': msg.timestamp,
                        'platform': msg.platform,
                        'message_id': msg.message_id,
                        'reply_to': msg.reply_to,
                        'created_at': msg.created_at,
                        'processed': msg.processed
                    }
                    for msg in messages
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询最近原始消息失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的最近原始消息: {e}") from e

    async def get_recent_filtered_messages(self, group_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取最近的筛选后消息

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            group_id: 群组ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 筛选后消息列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import FilteredMessage

                # 构建查询：按时间倒序
                stmt = select(FilteredMessage).where(
                    FilteredMessage.group_id == group_id
                ).order_by(
                    FilteredMessage.timestamp.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                messages = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询最近筛选消息: 群组={group_id}, 数量={len(messages)}")

                return [
                    {
                        'id': msg.id,
                        'raw_message_id': msg.raw_message_id,
                        'message': msg.message,
                        'sender_id': msg.sender_id,
                        'group_id': msg.group_id,
                        'timestamp': msg.timestamp,
                        'confidence': msg.confidence,
                        'quality_scores': msg.quality_scores,
                        'filter_reason': msg.filter_reason,
                        'created_at': msg.created_at,
                        'processed': msg.processed
                    }
                    for msg in messages
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询最近筛选消息失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的最近筛选消息: {e}") from e

    async def get_unprocessed_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取未处理的原始消息（ORM 版本 - 支持跨线程调用）

        Args:
            limit: 限制返回的消息数量

        Returns:
            未处理的消息列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import RawMessage

                # 构建查询
                stmt = select(RawMessage).where(
                    RawMessage.processed == False
                ).order_by(
                    RawMessage.timestamp.asc()
                )

                # 添加限制
                if limit:
                    stmt = stmt.limit(limit)

                # 执行查询
                result = await session.execute(stmt)
                raw_messages = result.scalars().all()

                # 转换为字典格式
                messages = []
                for msg in raw_messages:
                    messages.append({
                        'id': msg.id,
                        'sender_id': msg.sender_id,
                        'sender_name': msg.sender_name,
                        'message': msg.message,
                        'group_id': msg.group_id,
                        'platform': msg.platform,
                        'timestamp': msg.timestamp
                    })

                logger.debug(f"[SQLAlchemy] 获取到 {len(messages)} 条未处理消息")
                return messages

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取未处理消息失败: {e}", exc_info=True)
            raise RuntimeError(f"获取未处理消息失败: {str(e)}") from e

    async def mark_messages_processed(self, message_ids: List[int]) -> bool:
        """
        标记消息为已处理（ORM 版本 - 支持跨线程调用）

        Args:
            message_ids: 消息ID列表

        Returns:
            是否成功标记
        """
        if not message_ids:
            return True

        try:
            async with self.get_session() as session:
                from sqlalchemy import update
                from ..models.orm import RawMessage

                # 批量更新消息状态
                stmt = update(RawMessage).where(
                    RawMessage.id.in_(message_ids)
                ).values(
                    processed=True
                )

                result = await session.execute(stmt)
                await session.commit()

                updated_count = result.rowcount
                logger.debug(f"[SQLAlchemy] 已标记 {updated_count} 条消息为已处理")
                return True

        except Exception as e:
            logger.error(f"[SQLAlchemy] 标记消息处理状态失败: {e}", exc_info=True)
            raise RuntimeError(f"标记消息处理状态失败: {str(e)}") from e

    async def get_filtered_messages_for_learning(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取用于学习的筛选后消息

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            limit: 最大返回数量

        Returns:
            List[Dict]: 筛选后消息列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import FilteredMessage

                # 构建查询：获取未处理的高质量消息
                stmt = select(FilteredMessage).where(
                    FilteredMessage.processed == False
                ).order_by(
                    FilteredMessage.timestamp.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                messages = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询用于学习的筛选消息: 数量={len(messages)}")

                return [
                    {
                        'id': msg.id,
                        'raw_message_id': msg.raw_message_id,
                        'message': msg.message,
                        'sender_id': msg.sender_id,
                        'group_id': msg.group_id,
                        'timestamp': msg.timestamp,
                        'confidence': msg.confidence,
                        'quality_scores': msg.quality_scores,
                        'filter_reason': msg.filter_reason,
                        'created_at': msg.created_at,
                        'processed': msg.processed
                    }
                    for msg in messages
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询用于学习的筛选消息失败: {e}")
            raise RuntimeError(f"无法获取用于学习的筛选消息: {e}") from e

    async def get_recent_learning_batches(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取最近的学习批次

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            limit: 最大返回数量

        Returns:
            List[Dict]: 学习批次列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import LearningPerformanceHistory

                # 构建查询：按时间倒序
                stmt = select(LearningPerformanceHistory).order_by(
                    LearningPerformanceHistory.timestamp.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                batches = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询最近学习批次: 数量={len(batches)}")

                return [
                    {
                        'id': batch.id,
                        'group_id': batch.group_id,
                        'session_id': batch.session_id,
                        'timestamp': batch.timestamp,
                        'quality_score': batch.quality_score,
                        'learning_time': batch.learning_time,
                        'success': batch.success,
                        'successful_pattern': batch.successful_pattern,
                        'failed_pattern': batch.failed_pattern,
                        'created_at': batch.created_at
                    }
                    for batch in batches
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询最近学习批次失败: {e}")
            raise RuntimeError(f"无法获取最近学习批次: {e}") from e

    async def get_learning_sessions(self, group_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取学习会话

        使用 SQLAlchemy ORM 实现，支持跨线程调用（NullPool）

        Args:
            group_id: 群组ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 学习会话列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import LearningPerformanceHistory

                # 构建查询：按时间倒序，过滤群组
                stmt = select(LearningPerformanceHistory).where(
                    LearningPerformanceHistory.group_id == group_id
                ).order_by(
                    LearningPerformanceHistory.timestamp.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                sessions = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询学习会话: 群组={group_id}, 数量={len(sessions)}")

                return [
                    {
                        'id': session.id,
                        'group_id': session.group_id,
                        'session_id': session.session_id,
                        'timestamp': session.timestamp,
                        'quality_score': session.quality_score,
                        'learning_time': session.learning_time,
                        'success': session.success,
                        'successful_pattern': session.successful_pattern,
                        'failed_pattern': session.failed_pattern,
                        'created_at': session.created_at
                    }
                    for session in sessions
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 查询学习会话失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的学习会话: {e}") from e

    async def get_pending_persona_update_records(self) -> List[Dict[str, Any]]:
        """
        获取待审核的人格更新记录（ORM 版本）

        Returns:
            待审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.status == 'pending'
                ).order_by(
                    PersonaLearningReview.timestamp.desc()
                )

                result = await session.execute(stmt)
                records = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询待审核人格更新记录: 数量={len(records)}")

                return [
                    {
                        'id': record.id,
                        'timestamp': record.timestamp,
                        'group_id': record.group_id,
                        'update_type': record.update_type,
                        'original_content': record.original_content,
                        'new_content': record.new_content,
                        'reason': record.reason,
                        'status': record.status,
                        'reviewer_comment': record.reviewer_comment,
                        'review_time': record.review_time
                    }
                    for record in records
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取待审核人格更新记录失败: {e}")
            raise RuntimeError(f"无法获取待审核人格更新记录: {e}") from e

    async def save_persona_update_record(self, record: Dict[str, Any]) -> int:
        """
        保存人格更新记录（ORM 版本）

        Args:
            record: 人格更新记录字典

        Returns:
            int: 新记录 ID
        """
        try:
            async with self.get_session() as session:
                from ..models.orm import PersonaLearningReview

                orm_record = PersonaLearningReview(
                    timestamp=record.get('timestamp', time.time()),
                    group_id=record.get('group_id', 'default'),
                    update_type=record.get('update_type', 'prompt_update'),
                    original_content=record.get('original_content', ''),
                    new_content=record.get('new_content', ''),
                    proposed_content=record.get('new_content', ''),
                    confidence_score=record.get('confidence_score'),
                    reason=record.get('reason', ''),
                    status=record.get('status', 'pending'),
                    reviewer_comment=record.get('reviewer_comment'),
                    review_time=record.get('review_time')
                )

                session.add(orm_record)
                await session.flush()
                record_id = orm_record.id
                await session.commit()

                logger.debug(f"[SQLAlchemy] 已保存人格更新记录: id={record_id}")
                return record_id

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存人格更新记录失败: {e}")
            raise RuntimeError(f"无法保存人格更新记录: {e}") from e

    async def update_persona_update_record_status(
        self,
        record_id: int,
        status: str,
        reviewer_comment: Optional[str] = None
    ) -> bool:
        """
        更新人格更新记录状态（ORM 版本）

        Args:
            record_id: 记录 ID
            status: 新状态
            reviewer_comment: 审核备注

        Returns:
            bool: 是否更新成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if not record:
                    logger.warning(f"[SQLAlchemy] 未找到人格更新记录: id={record_id}")
                    return False

                record.status = status
                record.reviewer_comment = reviewer_comment
                record.review_time = time.time()

                await session.commit()
                logger.debug(f"[SQLAlchemy] 已更新人格记录状态: id={record_id}, status={status}")
                return True

        except Exception as e:
            logger.error(f"[SQLAlchemy] 更新人格更新记录状态失败: {e}")
            raise RuntimeError(f"无法更新人格更新记录状态: {e}") from e

    async def delete_persona_update_record(self, record_id: int) -> bool:
        """
        删除人格更新记录（ORM 版本）

        Args:
            record_id: 记录 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if not record:
                    logger.warning(f"[SQLAlchemy] 删除失败，记录不存在: id={record_id}")
                    return False

                await session.delete(record)
                await session.commit()
                logger.debug(f"[SQLAlchemy] 已删除人格更新记录: id={record_id}")
                return True

        except Exception as e:
            logger.error(f"[SQLAlchemy] 删除人格更新记录失败: {e}")
            raise RuntimeError(f"无法删除人格更新记录: {e}") from e

    async def get_persona_update_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """
        根据 ID 获取人格更新记录（ORM 版本）

        Args:
            record_id: 记录 ID

        Returns:
            Optional[Dict]: 记录字典，不存在时返回 None
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import PersonaLearningReview

                stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.id == record_id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if not record:
                    return None

                return {
                    'id': record.id,
                    'timestamp': record.timestamp,
                    'group_id': record.group_id,
                    'update_type': record.update_type,
                    'original_content': record.original_content,
                    'new_content': record.new_content,
                    'reason': record.reason,
                    'status': record.status,
                    'reviewer_comment': record.reviewer_comment,
                    'review_time': record.review_time
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 根据ID获取人格更新记录失败: {e}")
            raise RuntimeError(f"无法获取人格更新记录: {e}") from e

    async def get_reviewed_persona_update_records(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取已审核的人格更新记录（ORM 版本）

        Args:
            limit: 返回数量限制
            offset: 偏移量
            status_filter: 筛选状态 ('approved' 或 'rejected')，None 表示返回所有已审核记录

        Returns:
            已审核记录列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, or_
                from ..models.orm import PersonaLearningReview

                # 构建查询
                if status_filter:
                    # 筛选特定状态
                    stmt = select(PersonaLearningReview).where(
                        PersonaLearningReview.status == status_filter
                    )
                else:
                    # 返回所有已审核记录（approved 或 rejected）
                    stmt = select(PersonaLearningReview).where(
                        or_(
                            PersonaLearningReview.status == 'approved',
                            PersonaLearningReview.status == 'rejected'
                        )
                    )

                stmt = stmt.order_by(
                    PersonaLearningReview.review_time.desc()
                ).limit(limit).offset(offset)

                result = await session.execute(stmt)
                records = result.scalars().all()

                logger.debug(
                    f"[SQLAlchemy] 查询已审核人格更新记录: 状态={status_filter}, 数量={len(records)}"
                )

                return [
                    {
                        'id': record.id,
                        'timestamp': record.timestamp,
                        'group_id': record.group_id,
                        'update_type': record.update_type,
                        'original_content': record.original_content,
                        'new_content': record.new_content,
                        'reason': record.reason,
                        'status': record.status,
                        'reviewer_comment': record.reviewer_comment,
                        'review_time': record.review_time
                    }
                    for record in records
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取已审核人格更新记录失败: {e}")
            raise RuntimeError(f"无法获取已审核人格更新记录: {e}") from e

    async def get_global_jargon_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取全局共享的黑话列表（ORM 版本）

        Args:
            limit: 返回数量限制

        Returns:
            全局黑话列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm import Jargon

                stmt = select(Jargon).where(
                    Jargon.is_jargon == True,
                    Jargon.is_global == True
                ).order_by(
                    Jargon.count.desc(),
                    Jargon.updated_at.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                jargon_list = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 查询全局黑话列表: 数量={len(jargon_list)}")

                return [
                    {
                        'id': jargon.id,
                        'content': jargon.content,
                        'meaning': jargon.meaning,
                        'is_jargon': jargon.is_jargon,
                        'count': jargon.count,
                        'last_inference_count': jargon.last_inference_count,
                        'is_complete': jargon.is_complete,
                        'is_global': jargon.is_global,
                        'chat_id': jargon.chat_id,
                        'updated_at': jargon.updated_at
                    }
                    for jargon in jargon_list
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取全局黑话列表失败: {e}")
            raise RuntimeError(f"无法获取全局黑话列表: {e}") from e

    async def get_groups_for_social_analysis(self) -> List[Dict[str, Any]]:
        """
        获取可用于社交关系分析的群组列表（ORM 版本）

        返回包含消息数、成员数、社交关系数的群组列表
        仅返回消息数 >= 10 的群组

        Returns:
            群组统计列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import RawMessage, SocialRelation

                # 使用 LEFT JOIN 一次性获取群组的消息数、成员数和社交关系数
                # 注意：这里需要处理 MySQL 和 SQLite 的字段差异
                stmt = select(
                    RawMessage.group_id,
                    func.count(func.distinct(RawMessage.id)).label('message_count'),
                    func.count(func.distinct(RawMessage.sender_id)).label('member_count'),
                    func.count(func.distinct(SocialRelation.id)).label('relation_count')
                ).select_from(RawMessage).outerjoin(
                    SocialRelation,
                    RawMessage.group_id == SocialRelation.group_id
                ).where(
                    RawMessage.group_id.isnot(None),
                    RawMessage.group_id != ''
                ).group_by(
                    RawMessage.group_id
                ).having(
                    func.count(func.distinct(RawMessage.id)) >= 10
                ).order_by(
                    func.count(func.distinct(RawMessage.id)).desc()
                )

                result = await session.execute(stmt)
                rows = result.all()

                logger.debug(f"[SQLAlchemy] 查询社交分析群组列表: 数量={len(rows)}")

                groups = []
                for row in rows:
                    try:
                        groups.append({
                            'group_id': row.group_id,
                            'message_count': row.message_count,
                            'member_count': row.member_count,
                            'relation_count': row.relation_count
                        })
                    except Exception as e:
                        logger.warning(f"处理群组数据行失败: {e}, 行数据: {row}")
                        continue

                return groups

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取社交分析群组列表失败: {e}")
            raise RuntimeError(f"无法获取社交分析群组列表: {e}") from e

    async def get_jargon_groups(self) -> List[Dict[str, Any]]:
        """
        获取包含黑话的群组列表（ORM 版本）

        Returns:
            包含黑话的群组列表，包括群组ID、黑话数量、已完成黑话数、全局黑话数
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func, case
                from ..models.orm import Jargon

                # 统计每个群组的黑话情况
                stmt = select(
                    Jargon.chat_id.label('group_id'),
                    func.count(Jargon.id).label('total_jargon'),
                    func.sum(case((Jargon.is_complete == True, 1), else_=0)).label('complete_jargon'),
                    func.sum(case((Jargon.is_global == True, 1), else_=0)).label('global_jargon')
                ).where(
                    Jargon.is_jargon == True
                ).group_by(
                    Jargon.chat_id
                ).order_by(
                    func.count(Jargon.id).desc()
                )

                result = await session.execute(stmt)
                rows = result.all()

                logger.debug(f"[SQLAlchemy] 查询黑话群组列表: 数量={len(rows)}")

                groups = []
                for row in rows:
                    try:
                        groups.append({
                            'group_id': row.group_id,
                            'total_jargon': row.total_jargon or 0,
                            'complete_jargon': row.complete_jargon or 0,
                            'global_jargon': row.global_jargon or 0
                        })
                    except Exception as e:
                        logger.warning(f"处理黑话群组数据行失败: {e}, 行数据: {row}")
                        continue

                return groups

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取黑话群组列表失败: {e}")
            raise RuntimeError(f"无法获取黑话群组列表: {e}") from e

    async def get_group_user_statistics(self, group_id: str) -> Dict[str, Dict[str, Any]]:
        """
        获取群组用户消息统计（ORM 版本）

        Args:
            group_id: 群组ID

        Returns:
            字典，key 为 user_id，value 包含 sender_name 和 message_count
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import RawMessage

                # 统计每个用户在该群组的消息总数
                stmt = select(
                    RawMessage.sender_id,
                    func.max(RawMessage.sender_name).label('sender_name'),
                    func.count(RawMessage.id).label('message_count')
                ).where(
                    RawMessage.group_id == group_id,
                    RawMessage.sender_id != 'bot'
                ).group_by(
                    RawMessage.sender_id
                )

                result = await session.execute(stmt)
                rows = result.all()

                logger.debug(f"[SQLAlchemy] 查询群组用户统计: group_id={group_id}, 用户数={len(rows)}")

                user_stats = {}
                for row in rows:
                    try:
                        sender_id = row.sender_id
                        if sender_id:
                            user_stats[sender_id] = {
                                'sender_name': row.sender_name or sender_id,
                                'message_count': row.message_count or 0
                            }
                    except Exception as row_error:
                        logger.warning(f"处理用户统计数据行失败: {row_error}, row: {row}")
                        continue

                return user_stats

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取群组用户统计失败: {e}")
            raise RuntimeError(f"无法获取群组 {group_id} 的用户统计: {e}") from e

    async def count_refined_messages(self) -> int:
        """
        统计提炼内容数量（ORM 版本 - 支持跨线程调用）

        Returns:
            提炼消息的数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import FilteredMessage

                # 统计 refined = True 的消息数量
                stmt = select(func.count(FilteredMessage.id)).where(
                    FilteredMessage.processed == True  # refined 字段在某些版本中是 processed
                )

                result = await session.execute(stmt)
                count = result.scalar() or 0

                logger.debug(f"[SQLAlchemy] 统计提炼消息数量: {count}")
                return count

        except Exception as e:
            logger.error(f"[SQLAlchemy] 统计提炼消息数量失败: {e}")
            return 0

    async def count_style_learning_patterns(self) -> int:
        """
        统计风格学习模式数量（ORM 版本 - 支持跨线程调用）

        Returns:
            风格学习模式的数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import StyleLearningPattern

                # 统计所有风格学习模式
                stmt = select(func.count(StyleLearningPattern.id))

                result = await session.execute(stmt)
                count = result.scalar() or 0

                logger.debug(f"[SQLAlchemy] 统计风格学习模式数量: {count}")
                return count

        except Exception as e:
            logger.error(f"[SQLAlchemy] 统计风格学习模式数量失败: {e}")
            return 0

    async def count_pending_persona_updates(self) -> int:
        """
        统计待审查的人格更新数量（ORM 版本 - 支持跨线程调用）

        Returns:
            待审查人格更新的数量
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import PersonaLearningReview

                # 统计 status = 'pending' 的记录
                stmt = select(func.count(PersonaLearningReview.id)).where(
                    PersonaLearningReview.status == 'pending'
                )

                result = await session.execute(stmt)
                count = result.scalar() or 0

                logger.debug(f"[SQLAlchemy] 统计待审查人格更新数量: {count}")
                return count

        except Exception as e:
            logger.error(f"[SQLAlchemy] 统计待审查人格更新数量失败: {e}")
            return 0

    def get_db_connection(self):
        """
        获取数据库连接（兼容性方法）

        ⚠️ 向后兼容策略：
        - 如果有传统数据库管理器，返回其连接（支持 cursor() 方法）
        - 否则返回 SQLAlchemy 会话工厂（不支持 cursor()）

        Returns:
            传统数据库连接或 AsyncSession 工厂
        """
        if self._legacy_db:
            logger.debug("[SQLAlchemy] get_db_connection() 被调用，返回传统数据库连接（兼容 cursor()）")
            return self._legacy_db.get_db_connection()
        else:
            logger.debug("[SQLAlchemy] get_db_connection() 被调用，返回 SQLAlchemy 会话工厂")
            return self.get_session()

    def __getattr__(self, name):
        """
        魔法方法：自动降级未实现的方法到传统数据库管理器

        当访问 SQLAlchemyDatabaseManager 中不存在的属性/方法时：
        1. 检查传统数据库管理器是否可用
        2. 如果可用，返回传统管理器的对应方法
        3. 如果不可用，抛出 AttributeError
        """
        # 避免无限递归
        if name in ('_legacy_db', '_started', 'config', 'context', 'engine'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # 如果传统数据库管理器可用，尝试从它获取属性
        if self._legacy_db and hasattr(self._legacy_db, name):
            attr = getattr(self._legacy_db, name)
            logger.debug(f"[SQLAlchemy] 方法 '{name}' 未实现 ORM 版本，降级到传统数据库管理器")
            return attr

        # 如果传统数据库管理器也没有这个属性，抛出 AttributeError
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}', "
            f"and legacy database manager is {'not available' if not self._legacy_db else 'missing this attribute'}"
        )
