"""
增强型数据库管理器 - 使用 SQLAlchemy 和 Repository 模式
与现有 DatabaseManager 接口兼容，可通过配置切换
"""
import time
import asyncio
import threading
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

    def _is_event_loop_error(self, error: Exception) -> bool:
        """
        检查是否为事件循环冲突错误

        Args:
            error: 异常对象

        Returns:
            bool: 是否为事件循环错误
        """
        error_msg = str(error)
        return (
            "attached to a different loop" in error_msg or
            "Event loop is closed" in error_msg or
            "different event loop" in error_msg
        )

    def _is_cross_thread_call(self) -> bool:
        """
        检查是否为跨线程调用

        Returns:
            bool: 如果当前线程不是主线程，返回 True
        """
        if self._main_thread_id is None:
            return False
        current_thread_id = threading.get_ident()
        return current_thread_id != self._main_thread_id

    async def _run_in_main_loop(self, coro):
        """
        在主事件循环中执行协程（处理跨线程调用）

        注意：这个方法应该从异步上下文调用

        Args:
            coro: 要执行的协程

        Returns:
            协程的返回值
        """
        # 如果在主线程中，直接执行
        if not self._is_cross_thread_call() or self._main_loop is None:
            return await coro

        # 跨线程调用：降级到传统实现
        # 因为 run_coroutine_threadsafe 需要在同步上下文中使用
        logger.debug("[SQLAlchemyDBManager] 检测到跨线程调用，将降级到传统数据库实现")
        raise RuntimeError("跨线程异步调用，需要降级到传统实现")

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
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None  # 保存主事件循环
        self._main_thread_id: Optional[int] = None  # 保存主线程ID

        # 创建传统 DatabaseManager 实例用于委托未实现的方法
        from .database_manager import DatabaseManager
        self._legacy_db: Optional[DatabaseManager] = None
        try:
            self._legacy_db = DatabaseManager(config, context)
            logger.info("[SQLAlchemyDBManager] 初始化完成（包含传统数据库管理器后备）")
        except Exception as e:
            logger.warning(f"[SQLAlchemyDBManager] 初始化传统数据库管理器失败: {e}，部分功能可能不可用")
            logger.info("[SQLAlchemyDBManager] 初始化完成")

    async def start(self) -> bool:
        """
        启动数据库管理器

        Returns:
            bool: 是否启动成功
        """
        if self._started:
            logger.warning("[SQLAlchemyDBManager] 已经启动，跳过")
            return True

        try:
            # 保存主事件循环和线程ID（用于跨线程调用检测）
            try:
                self._main_loop = asyncio.get_running_loop()
                self._main_thread_id = threading.get_ident()
                logger.debug(f"[SQLAlchemyDBManager] 主事件循环已保存，线程ID: {self._main_thread_id}")
            except RuntimeError:
                logger.warning("[SQLAlchemyDBManager] 无法获取当前事件循环，可能在非异步上下文中启动")

            # 启动传统数据库管理器（用于委托未实现的方法）
            if self._legacy_db:
                legacy_started = await self._legacy_db.start()
                if not legacy_started:
                    logger.warning("[SQLAlchemyDBManager] 传统数据库管理器启动失败，部分功能可能不可用")

            # 获取数据库 URL
            db_url = self._get_database_url()

            # 创建数据库引擎
            self.engine = DatabaseEngine(db_url, echo=False)

            # 创建表结构（如果不��在）
            await self.engine.create_tables()

            # 健康检查
            if await self.engine.health_check():
                logger.info("✅ [SQLAlchemyDBManager] 数据库启动成功")
                self._started = True
                return True
            else:
                logger.error("❌ [SQLAlchemyDBManager] 数据库健康检查失败")
                return False

        except Exception as e:
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
            # 停止传统数据库管理器
            if self._legacy_db:
                await self._legacy_db.stop()

            # 停止 SQLAlchemy 引擎
            if self.engine:
                await self.engine.close()

            self._started = False
            logger.info("✅ [SQLAlchemyDBManager] 数据库已停止")
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

    @asynccontextmanager
    async def get_session(self):
        """
        获取数据库会话（上下文管理器）

        用法:
            async with db_manager.get_session() as session:
                repo = AffectionRepository(session)
                result = await repo.get_by_id(1)
        """
        if not self._started or not self.engine:
            raise RuntimeError("数据库管理器未启动")

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
                current = await repo.get_affection(group_id, user_id)
                previous_level = current.level if current else 0
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
            # 降级到传统实现
            logger.warning(f"[SQLAlchemy] Repository 查询社交关系失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_user_social_relations(group_id, user_id)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取用户社交关系: SQLAlchemy 和传统数据库管理器都不可用") from e

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
            logger.warning(f"[SQLAlchemy] Repository 查询已审查人格更新失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_reviewed_persona_learning_updates(limit, offset, status_filter)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取已审查人格更新: SQLAlchemy 和传统数据库管理器都不可用") from e

    async def get_trends_data(self) -> Dict[str, Any]:
        """
        获取趋势数据

        优先使用 SQLAlchemy Repository 实现，基于现有数据计算趋势
        """
        try:
            # 检查是否为跨线程调用
            if self._is_cross_thread_call():
                logger.debug("[SQLAlchemy] 检测到跨线程调用 get_trends_data，降级到传统实现")
                if self._legacy_db:
                    return await self._legacy_db.get_trends_data()
                return {
                    "affection_trend": [],
                    "interaction_trend": [],
                    "learning_trend": []
                }

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

        except RuntimeError as e:
            # 捕获事件循环冲突错误
            if self._is_event_loop_error(e):
                logger.warning(f"[SQLAlchemy] 事件循环冲突，降级到传统实现")
                if self._legacy_db:
                    return await self._legacy_db.get_trends_data()
                # 返回空数据而不是崩溃
                return {
                    "affection_trend": [],
                    "interaction_trend": [],
                    "learning_trend": []
                }
            else:
                raise
        except Exception as e:
            # 其他异常：降级到传统实现
            logger.warning(f"[SQLAlchemy] Repository 计算趋势数据失败: {type(e).__name__}: {str(e)[:100]}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_trends_data()

            # 返回空数据而不是崩溃
            logger.error("[SQLAlchemy] 无法获取趋势数据: SQLAlchemy 和传统数据库管理器都不可用")
            return {
                "affection_trend": [],
                "interaction_trend": [],
                "learning_trend": []
            }

    async def get_style_learning_statistics(self) -> Dict[str, Any]:
        """
        获取风格学习统计

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现
        """
        try:
            async with self.get_session() as session:
                from ..repositories.learning_repository import StyleLearningReviewRepository

                repo = StyleLearningReviewRepository(session)
                statistics = await repo.get_statistics()

                logger.debug("[SQLAlchemy] 使用 Repository 计算风格学习统计")

                return statistics

        except Exception as e:
            logger.warning(f"[SQLAlchemy] Repository 计算风格学习统计失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_style_learning_statistics()

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取风格学习统计: SQLAlchemy 和传统数据库管理器都不可用") from e

    async def get_pending_persona_learning_reviews(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取待审查的人格学习更新

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现

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
            logger.warning(f"[SQLAlchemy] Repository 查询待审查人格更新失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_pending_persona_learning_reviews(limit)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取待审查人格更新: SQLAlchemy 和传统数据库管理器都不可用") from e

    async def get_pending_style_reviews(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取待审查的风格学习更新

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现

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
            logger.warning(f"[SQLAlchemy] Repository 查询待审查风格更新失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_pending_style_reviews(limit)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取待审查风格更新: SQLAlchemy 和传统数据库管理器都不可用") from e

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
            logger.warning(f"[SQLAlchemy] Repository 更新风格审查状态失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.update_style_review_status(review_id, status, reviewer_comment)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法更新风格审查状态: SQLAlchemy 和传统数据库管理器都不可用") from e

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
            logger.warning(f"[SQLAlchemy] Repository 删除人格学习审查失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.delete_persona_learning_review_by_id(review_id)

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法删除人格学习审查: SQLAlchemy 和传统数据库管理器都不可用") from e

    async def get_messages_statistics(self) -> Dict[str, Any]:
        """
        获取消息统计信息

        注意：此功能依赖 raw_messages 和 filtered_messages 表，
        目前无 ORM 模型，直接降级到传统实现

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            # 检查是否为跨线程调用
            if self._is_cross_thread_call():
                logger.debug("[SQLAlchemy] 检测到跨线程调用 get_messages_statistics，降级到传统实现")
                if self._legacy_db:
                    return await self._legacy_db.get_messages_statistics()
                return {
                    "total_messages": 0,
                    "filtered_messages": 0,
                    "filter_rate": 0.0
                }

            # TODO: 创建 RawMessage 和 FilteredMessage ORM 模型后实现
            # 目前直接降级到传统实现
            if self._legacy_db:
                return await self._legacy_db.get_messages_statistics()

            # 返回空统计
            return {
                "total_messages": 0,
                "filtered_messages": 0,
                "filter_rate": 0.0
            }

        except Exception as e:
            # 检查事件循环错误
            if self._is_event_loop_error(e):
                logger.warning("[SQLAlchemy] 获取消息统计时遇到事件循环冲突，降级到传统实现")
            else:
                logger.warning(f"[SQLAlchemy] 获取消息统计失败: {type(e).__name__}: {str(e)[:100]}")

            # 尝试降级
            if self._legacy_db and not self._is_cross_thread_call():
                try:
                    return await self._legacy_db.get_messages_statistics()
                except:
                    pass

            # 返回空统计而不是崩溃
            return {
                "total_messages": 0,
                "filtered_messages": 0,
                "filter_rate": 0.0
            }

    async def get_all_expression_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有群组的表达模式

        优先使用 SQLAlchemy Repository 实现，失败时降级到传统实现

        Returns:
            Dict[str, List[Dict[str, Any]]]: 群组ID -> 表达模式列表的映射
        """
        try:
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
            logger.warning(f"[SQLAlchemy] Repository 获取表达模式失败: {e}，降级到传统实现")
            if self._legacy_db and hasattr(self._legacy_db, 'get_all_expression_patterns'):
                return await self._legacy_db.get_all_expression_patterns()

            # 对于表达模式，返回空字典而不是抛出异常（WebUI 可以处理空数据）
            logger.error(f"[SQLAlchemy] 无法获取表达模式: SQLAlchemy 和传统数据库管理器都不可用")
            return {}

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
            logger.warning(f"[SQLAlchemy] Repository 获取表达模式统计失败: {e}，降级到传统实现")
            if self._legacy_db and hasattr(self._legacy_db, 'get_expression_patterns_statistics'):
                return await self._legacy_db.get_expression_patterns_statistics()

            # 返回空统计信息
            logger.error(f"[SQLAlchemy] 无法获取表达模式统计: SQLAlchemy 和传统数据库管理器都不可用")
            return {
                'total_count': 0,
                'avg_weight': 0.0,
                'group_count': 0,
                'latest_time': 0
            }

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
            logger.warning(f"[SQLAlchemy] Repository 获取群组表达模式失败: {e}，降级到传统实现")
            if self._legacy_db and hasattr(self._legacy_db, 'get_group_expression_patterns'):
                return await self._legacy_db.get_group_expression_patterns(group_id, limit)

            # 返回空列表
            logger.error(f"[SQLAlchemy] 无法获取群组表达模式: SQLAlchemy 和传统数据库管理器都不可用")
            return []

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
                from ..models.orm.social_relation import UserSocialRelationComponent
                import time

                # 解析 from_user 和 to_user（兼容旧格式 "group_id:user_id"）
                from_user = relation_data.get('from_user', '')
                to_user = relation_data.get('to_user', '')

                # 提取用户ID（如果包含 group_id:）
                from_user_id = from_user.split(':')[-1] if ':' in from_user else from_user
                to_user_id = to_user.split(':')[-1] if ':' in to_user else to_user

                # 创建新的社交关系组件
                component = UserSocialRelationComponent(
                    profile_id=0,  # 稍后关联 profile
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    group_id=group_id,
                    relation_type=relation_data.get('relation_type', 'unknown'),
                    value=float(relation_data.get('strength', 0.0)),
                    frequency=int(relation_data.get('frequency', 0)),
                    last_interaction=int(relation_data.get('last_interaction', time.time())),
                    created_at=int(time.time())
                )

                session.add(component)
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

                    # 转换参数格式（? → :1, :2...）
                    if params:
                        # 将 ? 占位符转换为命名参数
                        param_dict = {}
                        if isinstance(params, (list, tuple)):
                            sql_converted = sql
                            for i, param in enumerate(params):
                                param_name = f"param_{i}"
                                sql_converted = sql_converted.replace('?', f":{param_name}", 1)
                                param_dict[param_name] = param
                            self._result = await self.session.execute(text(sql_converted), param_dict)
                        else:
                            self._result = await self.session.execute(text(sql), params)
                    else:
                        self._result = await self.session.execute(text(sql))

                    self.rowcount = self._result.rowcount if hasattr(self._result, 'rowcount') else 0
                    return self

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

    async def save_learning_performance_record(self, record: Dict[str, Any]):
        """
        保存学习性能记录

        Args:
            record: 性能记录数据
        """
        try:
            # 这个方法在旧系统中存在，但在新系统中可能不需要
            # 暂时记录日志，不做实际操作
            logger.debug(f"[SQLAlchemy] 学习性能记录（暂不实现）: {record}")

        except Exception as e:
            logger.error(f"[SQLAlchemy] 保存学习性能记录失败: {e}", exc_info=True)

    async def get_group_messages_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取群组消息统计

        注意：UserConversationHistory ORM 模型暂无 processed 字段
        返回的 unprocessed_messages 和 processed_messages 将为 0

        Args:
            group_id: 群组ID

        Returns:
            Dict: 消息统计数据
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import UserConversationHistory

                # 统计总消息数
                total_stmt = select(func.count()).select_from(UserConversationHistory).where(
                    UserConversationHistory.group_id == group_id
                )
                total_result = await session.execute(total_stmt)
                total_messages = total_result.scalar() or 0

                # TODO: UserConversationHistory 暂无 processed 字段
                # 暂时返回未处理数 = 总数，已处理数 = 0
                return {
                    'total_messages': total_messages,
                    'unprocessed_messages': total_messages,  # 假设全部未处理
                    'processed_messages': 0
                }

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取消息统计失败: {e}", exc_info=True)
            return {'total_messages': 0, 'unprocessed_messages': 0, 'processed_messages': 0}

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

    async def get_recent_jargon_list(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的俚语列表

        Args:
            group_id: 群组ID
            limit: 返回数量限制

        Returns:
            List[Dict]: 俚语列表
        """
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ..models.orm.expression import ExpressionPattern

                stmt = select(ExpressionPattern).where(
                    ExpressionPattern.group_id == group_id
                ).order_by(
                    ExpressionPattern.last_active_time.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                patterns = result.scalars().all()

                return [
                    {
                        'situation': pattern.situation,
                        'expression': pattern.expression,
                        'weight': pattern.weight,
                        'last_active_time': pattern.last_active_time,
                        'group_id': pattern.group_id
                    }
                    for pattern in patterns
                ]

        except Exception as e:
            logger.error(f"[SQLAlchemy] 获取最近俚语列表失败: {e}", exc_info=True)
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

    async def save_learning_session_record(self, session_data: Dict[str, Any]) -> bool:
        """
        保存学习会话记录

        Args:
            session_data: 会话数据

        Returns:
            bool: 是否保存成功
        """
        try:
            # 此方法在新架构中可能不需要，暂时只记录日志
            logger.debug(f"[SQLAlchemy] 学习会话记录（暂不实现）: {session_data}")
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

    def __getattr__(self, name):
        """
        魔法方法：自动降级未实现的方法到传统数据库管理器

        当访问 SQLAlchemyDatabaseManager 中不存在的属性/方法时：
        1. 检查传统数据库管理器是否可用
        2. 如果可用，返回传统管理器的对应方法
        3. 如果不可用，抛出 AttributeError

        这样可以避免为每个传统方法都写一个包装函数
        """
        # 避免无限递归：_legacy_db 本身不应该触发 __getattr__
        if name == '_legacy_db':
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # 如果传统数据库管理器可用，尝试从它获取属性
        if self._legacy_db and hasattr(self._legacy_db, name):
            attr = getattr(self._legacy_db, name)
            logger.debug(f"[SQLAlchemy] 方法 '{name}' 未实现，自动降级到传统数据库管理器")
            return attr

        # 如果传统数据库管理器也没有这个属性，抛出 AttributeError
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}', "
            f"and legacy database manager is {'not available' if not self._legacy_db else 'missing this attribute'}"
        )
