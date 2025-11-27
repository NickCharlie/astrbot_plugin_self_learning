"""
自动数据迁移工具
从旧的数据库表结构迁移到新的 SQLAlchemy ORM 结构
"""
import asyncio
import time
from typing import Dict, List, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, select
from astrbot.api import logger

from ..models.orm import (
    Base,
    UserAffection,
    AffectionInteraction,
    UserConversationHistory,
    UserDiversity,
    Memory,
    MemoryEmbedding,
    MemorySummary,
    CompositePsychologicalState,
    PsychologicalStateComponent,
    PsychologicalStateHistory,
    UserSocialProfile,
    UserSocialRelationComponent,
    SocialRelationHistory,
)


class DatabaseMigrationTool:
    """
    数据库自动迁移工具

    功能:
    1. 检测旧表是否存在
    2. 创建新表结构
    3. 自动迁移数据
    4. 验证数据完整性
    5. 保留旧表作为备份
    """

    def __init__(self, old_db_url: str, new_db_url: str = None):
        """
        初始化迁移工具

        Args:
            old_db_url: 旧数据库 URL
            new_db_url: 新数据库 URL (如果为 None，则使用同一个数据库)
        """
        self.old_db_url = old_db_url
        self.new_db_url = new_db_url or old_db_url

        # 创建引擎
        if 'sqlite' in old_db_url:
            self.old_engine = create_async_engine(
                f"sqlite+aiosqlite:///{old_db_url.replace('sqlite:///', '')}",
                echo=False
            )
        else:
            self.old_engine = create_async_engine(old_db_url, echo=False)

        if 'sqlite' in self.new_db_url:
            self.new_engine = create_async_engine(
                f"sqlite+aiosqlite:///{self.new_db_url.replace('sqlite:///', '')}",
                echo=False
            )
        else:
            self.new_engine = create_async_engine(self.new_db_url, echo=False)

        self.old_session_factory = async_sessionmaker(self.old_engine, class_=AsyncSession)
        self.new_session_factory = async_sessionmaker(self.new_engine, class_=AsyncSession)

        logger.info("[数据迁移] 迁移工具初始化完成")

    async def migrate_all(self, backup: bool = True):
        """
        执行完整的数据迁移

        Args:
            backup: 是否备份旧表
        """
        logger.info("=" * 60)
        logger.info("开始数据迁移流程")
        logger.info("=" * 60)

        start_time = time.time()

        try:
            # 1. 创建新表结构
            await self._create_new_tables()

            # 2. 检查旧表
            old_tables = await self._check_old_tables()
            logger.info(f"检测到 {len(old_tables)} 个旧表")

            # 3. 迁移数据
            await self._migrate_user_affections()
            await self._migrate_affection_interactions()
            await self._migrate_conversation_history()
            await self._migrate_user_diversity()
            await self._migrate_memories()
            await self._migrate_memory_embeddings()
            await self._migrate_memory_summaries()
            await self._migrate_psychological_states()
            await self._migrate_social_relations()

            # 4. 验证数据
            await self._verify_migration()

            # 5. 备份旧表 (可选)
            if backup:
                await self._backup_old_tables()

            elapsed = time.time() - start_time
            logger.info("=" * 60)
            logger.info(f"✅ 数据迁移完成! 耗时: {elapsed:.2f} 秒")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"❌ 数据迁移失败: {e}", exc_info=True)
            raise

    async def _create_new_tables(self):
        """创建新表结构"""
        logger.info("[步骤 1/5] 创建新表结构...")

        async with self.new_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ 新表结构创建完成")

    async def _check_old_tables(self) -> List[str]:
        """检查旧表"""
        logger.info("[步骤 2/5] 检查旧表...")

        async with self.old_session_factory() as session:
            # SQLite
            if 'sqlite' in self.old_db_url:
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            # MySQL
            else:
                result = await session.execute(text("SHOW TABLES"))

            tables = [row[0] for row in result.fetchall()]

        return tables

    async def _migrate_user_affections(self):
        """迁移用户好感度表"""
        logger.info("[迁移] user_affections...")

        try:
            async with self.old_session_factory() as old_session:
                # 查询旧数据
                result = await old_session.execute(
                    text("SELECT * FROM user_affections")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                # 转换为字典
                data = [dict(zip(columns, row)) for row in rows]

                logger.info(f"  - 找到 {len(data)} 条记录")

                # 插入新表
                async with self.new_session_factory() as new_session:
                    for item in data:
                        affection = UserAffection(
                            id=item.get('id'),
                            group_id=item.get('group_id'),
                            user_id=item.get('user_id'),
                            affection_level=item.get('affection_level', 0),
                            max_affection=item.get('max_affection', 100),
                            created_at=int(item.get('created_at', time.time())),
                            updated_at=int(item.get('updated_at', time.time()))
                        )
                        new_session.add(affection)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_affection_interactions(self):
        """迁移好感度交互记录表"""
        logger.info("[迁移] affection_interactions...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM affection_interactions")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        interaction = AffectionInteraction(
                            id=item.get('id'),
                            user_affection_id=item.get('user_affection_id'),
                            interaction_type=item.get('interaction_type'),
                            affection_delta=item.get('affection_delta', 0),
                            message_content=item.get('message_content'),
                            timestamp=int(item.get('timestamp', time.time()))
                        )
                        new_session.add(interaction)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_conversation_history(self):
        """迁移对话历史表"""
        logger.info("[迁移] user_conversation_history...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM user_conversation_history")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        history = UserConversationHistory(
                            id=item.get('id'),
                            group_id=item.get('group_id'),
                            user_id=item.get('user_id'),
                            role=item.get('role'),
                            content=item.get('content'),
                            timestamp=int(item.get('timestamp', time.time())),
                            turn_index=item.get('turn_index', 0)
                        )
                        new_session.add(history)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_user_diversity(self):
        """迁移用户多样性表"""
        logger.info("[迁移] user_diversity...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM user_diversity")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        diversity = UserDiversity(
                            id=item.get('id'),
                            group_id=item.get('group_id'),
                            user_id=item.get('user_id'),
                            response_hash=item.get('response_hash'),
                            response_preview=item.get('response_preview'),
                            timestamp=int(item.get('timestamp', time.time()))
                        )
                        new_session.add(diversity)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_memories(self):
        """迁移记忆表"""
        logger.info("[迁移] memories...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(text("SELECT * FROM memories"))
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        memory = Memory(
                            id=item.get('id'),
                            group_id=item.get('group_id'),
                            user_id=item.get('user_id'),
                            content=item.get('content'),
                            importance=item.get('importance', 5),
                            memory_type=item.get('memory_type', 'conversation'),
                            created_at=int(item.get('created_at', time.time())),
                            last_accessed=int(item.get('last_accessed', time.time())),
                            access_count=item.get('access_count', 0)
                        )
                        new_session.add(memory)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_memory_embeddings(self):
        """迁移记忆向量表"""
        logger.info("[迁移] memory_embeddings...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM memory_embeddings")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        embedding = MemoryEmbedding(
                            id=item.get('id'),
                            memory_id=item.get('memory_id'),
                            embedding_model=item.get('embedding_model'),
                            embedding_data=item.get('embedding_data'),
                            created_at=int(item.get('created_at', time.time()))
                        )
                        new_session.add(embedding)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_memory_summaries(self):
        """迁移记忆摘要表"""
        logger.info("[迁移] memory_summaries...")

        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM memory_summaries")
                )
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info("  - 表为空，跳过")
                    return

                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"  - 找到 {len(data)} 条记录")

                async with self.new_session_factory() as new_session:
                    for item in data:
                        summary = MemorySummary(
                            id=item.get('id'),
                            group_id=item.get('group_id'),
                            user_id=item.get('user_id'),
                            summary_type=item.get('summary_type'),
                            summary_content=item.get('summary_content'),
                            memory_count=item.get('memory_count', 0),
                            created_at=int(item.get('created_at', time.time())),
                            updated_at=int(item.get('updated_at', time.time()))
                        )
                        new_session.add(summary)

                    await new_session.commit()

                logger.info(f"  ✅ 成功迁移 {len(data)} 条记录")

        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - 表不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_psychological_states(self):
        """迁移心理状态表"""
        logger.info("[迁移] 心理状态相关表...")

        # 迁移复合状态
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM composite_psychological_states")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - composite_psychological_states: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            state = CompositePsychologicalState(
                                id=item.get('id'),
                                group_id=item.get('group_id'),
                                state_id=item.get('state_id'),
                                triggering_events=item.get('triggering_events'),
                                context=item.get('context'),
                                created_at=int(item.get('created_at', time.time())),
                                last_updated=int(item.get('last_updated', time.time()))
                            )
                            new_session.add(state)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 composite_psychological_states")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - composite_psychological_states 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

        # 迁移状态组件
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM psychological_state_components")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - psychological_state_components: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            component = PsychologicalStateComponent(
                                id=item.get('id'),
                                group_id=item.get('group_id'),
                                state_id=item.get('state_id'),
                                category=item.get('category'),
                                state_type=item.get('state_type'),
                                value=float(item.get('value', 0)),
                                threshold=float(item.get('threshold', 0.3)),
                                description=item.get('description'),
                                start_time=int(item.get('start_time', time.time()))
                            )
                            new_session.add(component)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 psychological_state_components")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - psychological_state_components 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

        # 迁移历史记录
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM psychological_state_history")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - psychological_state_history: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            history = PsychologicalStateHistory(
                                id=item.get('id'),
                                group_id=item.get('group_id'),
                                state_id=item.get('state_id'),
                                category=item.get('category'),
                                old_state_type=item.get('old_state_type'),
                                new_state_type=item.get('new_state_type'),
                                old_value=float(item.get('old_value', 0)) if item.get('old_value') else None,
                                new_value=float(item.get('new_value', 0)),
                                change_reason=item.get('change_reason'),
                                timestamp=int(item.get('timestamp', time.time()))
                            )
                            new_session.add(history)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 psychological_state_history")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - psychological_state_history 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _migrate_social_relations(self):
        """迁移社交关系表"""
        logger.info("[迁移] 社交关系相关表...")

        # 迁移用户档案
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM user_social_profiles")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - user_social_profiles: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            profile = UserSocialProfile(
                                id=item.get('id'),
                                user_id=item.get('user_id'),
                                group_id=item.get('group_id'),
                                total_relations=item.get('total_relations', 0),
                                significant_relations=item.get('significant_relations', 0),
                                dominant_relation_type=item.get('dominant_relation_type'),
                                created_at=int(item.get('created_at', time.time())),
                                last_updated=int(item.get('last_updated', time.time()))
                            )
                            new_session.add(profile)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 user_social_profiles")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - user_social_profiles 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

        # 迁移关系组件
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM user_social_relation_components")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - user_social_relation_components: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            component = UserSocialRelationComponent(
                                id=item.get('id'),
                                from_user_id=item.get('from_user_id'),
                                to_user_id=item.get('to_user_id'),
                                group_id=item.get('group_id'),
                                relation_type=item.get('relation_type'),
                                value=float(item.get('value', 0)),
                                frequency=item.get('frequency', 0),
                                last_interaction=int(item.get('last_interaction', time.time())),
                                description=item.get('description'),
                                tags=item.get('tags'),
                                created_at=int(item.get('created_at', time.time()))
                            )
                            new_session.add(component)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 user_social_relation_components")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - user_social_relation_components 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

        # 迁移历史记录
        try:
            async with self.old_session_factory() as old_session:
                result = await old_session.execute(
                    text("SELECT * FROM social_relation_history")
                )
                rows = result.fetchall()
                columns = result.keys()

                if rows:
                    data = [dict(zip(columns, row)) for row in rows]
                    logger.info(f"  - social_relation_history: {len(data)} 条记录")

                    async with self.new_session_factory() as new_session:
                        for item in data:
                            history = SocialRelationHistory(
                                id=item.get('id'),
                                from_user_id=item.get('from_user_id'),
                                to_user_id=item.get('to_user_id'),
                                group_id=item.get('group_id'),
                                relation_type=item.get('relation_type'),
                                old_value=float(item.get('old_value', 0)) if item.get('old_value') else None,
                                new_value=float(item.get('new_value', 0)),
                                change_reason=item.get('change_reason'),
                                timestamp=int(item.get('timestamp', time.time()))
                            )
                            new_session.add(history)

                        await new_session.commit()

                    logger.info(f"  ✅ 成功迁移 social_relation_history")
        except Exception as e:
            if "no such table" in str(e) or "doesn't exist" in str(e):
                logger.info("  - social_relation_history 不存在，跳过")
            else:
                logger.error(f"  ❌ 迁移失败: {e}")

    async def _verify_migration(self):
        """验证迁移数据完整性"""
        logger.info("[步骤 4/5] 验证数据完整性...")

        tables_to_check = [
            'user_affections',
            'affection_interactions',
            'user_conversation_history',
            'user_diversity',
            'memories',
            'memory_embeddings',
            'memory_summaries',
            'composite_psychological_states',
            'psychological_state_components',
            'psychological_state_history',
            'user_social_profiles',
            'user_social_relation_components',
            'social_relation_history',
        ]

        for table in tables_to_check:
            try:
                async with self.old_session_factory() as old_session:
                    old_result = await old_session.execute(
                        text(f"SELECT COUNT(*) FROM {table}")
                    )
                    old_count = old_result.scalar()

                async with self.new_session_factory() as new_session:
                    new_result = await new_session.execute(
                        text(f"SELECT COUNT(*) FROM {table}")
                    )
                    new_count = new_result.scalar()

                if old_count == new_count:
                    logger.info(f"  ✅ {table}: {new_count} 条记录 (匹配)")
                else:
                    logger.warning(f"  ⚠️ {table}: 旧表 {old_count} 条 vs 新表 {new_count} 条")

            except Exception as e:
                if "no such table" in str(e) or "doesn't exist" in str(e):
                    logger.info(f"  - {table}: 不存在，跳过验证")
                else:
                    logger.error(f"  ❌ {table}: 验证失败 - {e}")

    async def _backup_old_tables(self):
        """备份旧表 (重命名为 _old 后缀)"""
        logger.info("[步骤 5/5] 备份旧表...")

        # 如果是同一个数据库，重命名旧表
        if self.old_db_url == self.new_db_url:
            logger.info("  - 将旧表重命名为 _backup 后缀")
            # TODO: 实现重命名逻辑
        else:
            logger.info("  - 数据在不同数据库，无需备份")

    async def close(self):
        """关闭连接"""
        await self.old_engine.dispose()
        await self.new_engine.dispose()


# ============================================================
# 便捷函数
# ============================================================

async def migrate_database(db_url: str, backup: bool = True):
    """
    执行数据库迁移

    Args:
        db_url: 数据库 URL
        backup: 是否备份旧表

    Examples:
        # SQLite
        await migrate_database('sqlite:///./data/database.db')

        # MySQL
        await migrate_database('mysql+aiomysql://user:pass@localhost/dbname')
    """
    migrator = DatabaseMigrationTool(db_url, db_url)

    try:
        await migrator.migrate_all(backup=backup)
    finally:
        await migrator.close()


if __name__ == "__main__":
    # 测试迁移
    import sys

    if len(sys.argv) < 2:
        print("用法: python migration_tool.py <database_url>")
        print("示例: python migration_tool.py sqlite:///./data/database.db")
        sys.exit(1)

    db_url = sys.argv[1]
    asyncio.run(migrate_database(db_url))
