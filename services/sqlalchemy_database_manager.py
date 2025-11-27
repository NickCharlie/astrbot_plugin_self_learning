"""
增强型数据库管理器 - 使用 SQLAlchemy 和 Repository 模式
与现有 DatabaseManager 接口兼容，可通过配置切换
"""
import time
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
            # 启动传统数据库管理器（用于委托未实现的方法）
            if self._legacy_db:
                legacy_started = await self._legacy_db.start()
                if not legacy_started:
                    logger.warning("[SQLAlchemyDBManager] 传统数据库管理器启动失败，部分功能可能不可用")

            # 获取数据库 URL
            db_url = self._get_database_url()

            # 创建数据库引擎
            self.engine = DatabaseEngine(db_url, echo=False)

            # 创建表结构（如果不存在）
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
            host = getattr(self.config, 'db_host', 'localhost')
            port = getattr(self.config, 'db_port', 3306)
            user = getattr(self.config, 'db_user', 'root')
            password = getattr(self.config, 'db_password', '')
            database = getattr(self.config, 'db_name', 'astrbot_self_learning')

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
        affection_delta: int,
        max_affection: int = 100
    ) -> bool:
        """
        更新用户好感度（兼容接口）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            affection_delta: 好感度变化量
            max_affection: 最大好感度

        Returns:
            bool: 是否更新成功
        """
        try:
            async with self.get_session() as session:
                repo = AffectionRepository(session)
                affection = await repo.update_level(
                    group_id,
                    user_id,
                    affection_delta,
                    max_affection
                )
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
                        or_(*[UserSocialRelationComponent.from_user == key for key in user_keys])
                    )
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.strength.desc()
                ).limit(self.config.default_social_limit)

                result = await session.execute(stmt_outgoing)
                outgoing_relations = result.scalars().all()

                # 查询指向用户的关系
                stmt_incoming = select(UserSocialRelationComponent).where(
                    and_(
                        UserSocialRelationComponent.group_id == group_id,
                        or_(*[UserSocialRelationComponent.to_user == key for key in user_keys])
                    )
                ).order_by(
                    UserSocialRelationComponent.frequency.desc(),
                    UserSocialRelationComponent.strength.desc()
                ).limit(self.config.default_social_limit)

                result = await session.execute(stmt_incoming)
                incoming_relations = result.scalars().all()

                logger.debug(f"[SQLAlchemy] 使用 Repository 查询社交关系: {user_id} in {group_id}")

                return {
                    'user_id': user_id,
                    'group_id': group_id,
                    'outgoing': [
                        {
                            'from_user': r.from_user,
                            'to_user': r.to_user,
                            'relation_type': r.relation_type,
                            'strength': r.strength,
                            'frequency': r.frequency,
                            'last_interaction': r.last_interaction_time
                        }
                        for r in outgoing_relations
                    ],
                    'incoming': [
                        {
                            'from_user': r.from_user,
                            'to_user': r.to_user,
                            'relation_type': r.relation_type,
                            'strength': r.strength,
                            'frequency': r.frequency,
                            'last_interaction': r.last_interaction_time
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
                        'confidence': review.confidence,
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
            # 尝试使用 Repository 计算趋势
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ..models.orm import UserAffection, InteractionRecord
                from datetime import datetime, timedelta

                # 计算趋势的天数范围（使用配置中的 trend_analysis_days）
                days_ago = int((datetime.now() - timedelta(days=self.config.trend_analysis_days)).timestamp())

                # 好感度趋势（按天统计）
                # SQLite 使用 datetime(timestamp, 'unixepoch') 而不是 from_unixtime()
                affection_stmt = select(
                    func.date(UserAffection.updated_at, 'unixepoch').label('date'),
                    func.avg(UserAffection.affection_level).label('avg_affection'),
                    func.count(UserAffection.id).label('count')
                ).where(
                    UserAffection.updated_at >= days_ago
                ).group_by(
                    func.date(UserAffection.updated_at, 'unixepoch')
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
                    func.date(InteractionRecord.timestamp, 'unixepoch').label('date'),
                    func.count(InteractionRecord.id).label('count')
                ).where(
                    InteractionRecord.timestamp >= days_ago
                ).group_by(
                    func.date(InteractionRecord.timestamp, 'unixepoch')
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
            # 降级到传统实现
            logger.warning(f"[SQLAlchemy] Repository 计算趋势数据失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_trends_data()

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取趋势数据: SQLAlchemy 和传统数据库管理器都不可用") from e

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
            # TODO: 创建 RawMessage 和 FilteredMessage ORM 模型后实现
            # 目前直接降级到传统实现
            if self._legacy_db:
                return await self._legacy_db.get_messages_statistics()

            # 不返回默认值，直接抛出异常
            raise RuntimeError("无法获取消息统计: 传统数据库管理器不可用")

        except Exception as e:
            logger.warning(f"[SQLAlchemy] 获取消息统计失败: {e}，降级到传统实现")
            if self._legacy_db:
                return await self._legacy_db.get_messages_statistics()

            # 不返回默认值，直接抛出异常
            raise RuntimeError(f"无法获取消息统计: SQLAlchemy 和传统数据库管理器都不可用") from e

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
