"""
智能数据库迁移工具 v2.0
- 自动检测字段
- 类型转换容错
- 自动创建缺失表
- 详细的错误日志
"""
import asyncio
import time
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
from astrbot.api import logger  # 使用 astrbot 框架的 logger

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
    SocialRelationAnalysisResult,
    SocialNetworkNode,
    SocialNetworkEdge
)


class SmartDatabaseMigrator:
    """
    智能数据库迁移工具

    特性:
    1. 自动检测旧表是否存在
    2. 自动创建缺失的新表
    3. 智能字段映射和类型转换
    4. 详细的错误日志
    5. 逐行容错处理
    6. 支持跨数据库迁移（SQLite → MySQL）
    """

    def __init__(self, source_db_url: str, target_db_url: str = None):
        """
        初始化迁移工具

        Args:
            source_db_url: 源数据库 URL (支持 SQLite 和 MySQL)
            target_db_url: 目标数据库 URL (如果为 None，则使用源数据库，用于in-place迁移)
        """
        self.source_db_url = source_db_url
        self.target_db_url = target_db_url or source_db_url

        # 判断是否为跨数据库迁移
        self.is_cross_db_migration = (source_db_url != self.target_db_url)

        # 创建源数据库引擎
        if 'sqlite' in source_db_url:
            if not source_db_url.startswith('sqlite+aiosqlite'):
                source_db_url = f"sqlite+aiosqlite:///{source_db_url.replace('sqlite:///', '')}"

        self.source_engine = create_async_engine(source_db_url, echo=False)
        self.source_session_factory = async_sessionmaker(
            self.source_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # 创建目标数据库引擎
        target_url = self.target_db_url
        if 'sqlite' in target_url:
            if not target_url.startswith('sqlite+aiosqlite'):
                target_url = f"sqlite+aiosqlite:///{target_url.replace('sqlite:///', '')}"

        self.target_engine = create_async_engine(target_url, echo=False)
        self.target_session_factory = async_sessionmaker(
            self.target_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # 表映射配置 - ORM 模型表
        self.table_models = {
            'user_affections': UserAffection,
            'affection_interactions': AffectionInteraction,
            'user_conversation_history': UserConversationHistory,
            'user_diversity': UserDiversity,
            'memories': Memory,
            'memory_embeddings': MemoryEmbedding,
            'memory_summaries': MemorySummary,
            'composite_psychological_states': CompositePsychologicalState,
            'psychological_state_components': PsychologicalStateComponent,
            'psychological_state_history': PsychologicalStateHistory,
            'user_social_profiles': UserSocialProfile,
            'user_social_relation_components': UserSocialRelationComponent,
            'social_relation_history': SocialRelationHistory,
        }

        # 传统 DatabaseManager 管理的表（无 ORM 模型）
        self.traditional_tables = [
            'raw_messages',              # 原始消息
            'bot_messages',              # Bot 消息
            'filtered_messages',         # 筛选后消息
            'learning_batches',          # 学习批次
            'persona_update_records',    # 人格更新记录
            'reinforcement_learning_results',  # 强化学习结果
            'strategy_optimization_results',   # 策略优化结果
            'learning_performance_history',    # 学习性能历史
            'llm_call_statistics',       # LLM 调用统计
            'jargon',                    # 黑话/术语
            'social_relations',          # 社交关系
            'expression_patterns',       # 表达模式
            'language_style_patterns',   # 语言风格模式
            'topic_summaries',           # 话题摘要
            'style_learning_records',    # 风格学习记录
            'style_learning_reviews',    # 风格学习审核
            'persona_fusion_history',    # 人格融合历史
            'persona_update_reviews',    # 人格更新审核
        ]

        if self.is_cross_db_migration:
            logger.info(f"🚀 [数据迁移] 跨数据库迁移模式")
            logger.info(f"   源数据库: {self._mask_url(source_db_url)}")
            logger.info(f"   目标数据库: {self._mask_url(self.target_db_url)}")
        else:
            logger.info("🚀 [数据迁移] 本地迁移模式 (In-place)")

    def _mask_url(self, url: str) -> str:
        """隐藏数据库 URL 中的密码"""
        if '@' in url:
            # mysql+aiomysql://user:password@host:port/db
            parts = url.split('@')
            if ':' in parts[0]:
                prefix = parts[0].rsplit(':', 1)[0]
                return f"{prefix}:****@{parts[1]}"
        return url

    async def migrate_all(self):
        """执行完整的智能迁移"""
        logger.info("=" * 70)
        logger.info("🔄 开始智能数据迁移流程")
        logger.info("=" * 70)

        start_time = time.time()

        try:
            # 1. 创建新表结构
            await self._create_tables()

            # 2. 检测现有表
            existing_tables = await self._detect_existing_tables()
            logger.info(f"📊 检测到 {len(existing_tables)} 个现有表")

            # 3. 逐表迁移数据 - ORM 模型表
            total_migrated = 0
            logger.info(f"📦 [步骤 3/5] 迁移 ORM 模型表...")
            for table_name, model_class in self.table_models.items():
                if table_name in existing_tables:
                    count = await self._migrate_table(table_name, model_class)
                    total_migrated += count
                else:
                    logger.info(f"[迁移] {table_name} - 不存在于旧数据库，已创建空表")

            # 4. 迁移传统表（无 ORM 模型）
            logger.info(f"📦 [步骤 4/5] 迁移传统表（无 ORM 模型）...")
            for table_name in self.traditional_tables:
                if table_name in existing_tables:
                    count = await self._migrate_traditional_table(table_name)
                    total_migrated += count
                else:
                    logger.info(f"[迁移] {table_name} - 不存在于旧数据库，跳过")

            # 5. 验证迁移
            await self._verify_migration()

            elapsed = time.time() - start_time
            logger.info("=" * 70)
            logger.info(f"✅ 数据迁移完成！")
            logger.info(f"📊 共迁移 {total_migrated} 条记录")
            logger.info(f"⏱️  耗时: {elapsed:.2f} 秒")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"❌ 数据迁移失败: {e}", exc_info=True)
            raise

    async def _create_tables(self):
        """创建新表结构"""
        logger.info("📝 [步骤 1/5] 创建/更新表结构...")

        async with self.target_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 修复旧表缺失字段
        await self._fix_legacy_table_schema()

        logger.info("✅ 表结构准备完成")

    async def _fix_legacy_table_schema(self):
        """修复旧表缺失的字段（向后兼容）"""
        logger.info("🔧 [修复] 检查并修复旧表缺失字段...")

        is_sqlite = 'sqlite' in self.target_db_url.lower()

        # 需要修复的表和字段定义
        fixes = {
            'style_learning_reviews': [
                ('reviewer_comment', 'TEXT' if is_sqlite else 'TEXT'),
                ('review_time', 'REAL' if is_sqlite else 'DOUBLE'),
            ],
            'persona_update_reviews': [
                ('reviewer_comment', 'TEXT' if is_sqlite else 'TEXT'),
                ('review_time', 'REAL' if is_sqlite else 'DOUBLE'),
            ],
        }

        async with self.target_session_factory() as session:
            for table_name, columns_to_add in fixes.items():
                try:
                    # 检查表是否存在
                    check_query = text(f"SELECT name FROM {'sqlite_master' if is_sqlite else 'information_schema.tables'} WHERE {'type' if is_sqlite else 'table_type'}='{'table' if is_sqlite else 'BASE TABLE'}' AND {'name' if is_sqlite else 'table_name'}=:table_name")
                    result = await session.execute(check_query, {'table_name': table_name})
                    if not result.fetchone():
                        logger.debug(f"  ├─ {table_name}: 表不存在，跳过修复")
                        continue

                    # 获取现有列
                    if is_sqlite:
                        pragma_result = await session.execute(text(f"PRAGMA table_info({table_name})"))
                        existing_columns = {row[1] for row in pragma_result.fetchall()}
                    else:
                        # MySQL
                        col_result = await session.execute(
                            text(f"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME=:table_name"),
                            {'table_name': table_name}
                        )
                        existing_columns = {row[0] for row in col_result.fetchall()}

                    # 添加缺失字段
                    for col_name, col_type in columns_to_add:
                        if col_name not in existing_columns:
                            try:
                                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                                await session.execute(text(alter_sql))
                                await session.commit()
                                logger.info(f"  ├─ {table_name}.{col_name}: 字段已添加 ({col_type})")
                            except Exception as e:
                                logger.warning(f"  ├─ {table_name}.{col_name}: 添加失败 - {e}")
                        else:
                            logger.debug(f"  ├─ {table_name}.{col_name}: 字段已存在")

                except Exception as e:
                    logger.warning(f"  ├─ {table_name}: 修复失败 - {e}")

        logger.info("  └─ 字段修复完成")

    async def _detect_existing_tables(self) -> List[str]:
        """检测源数据库中的现有表"""
        logger.info("🔍 [步骤 2/5] 检测源数据库中的现有表...")

        async with self.source_session_factory() as session:
            if 'sqlite' in self.source_db_url:
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            else:
                result = await session.execute(text("SHOW TABLES"))

            tables = [row[0] for row in result.fetchall()]

        return tables

    async def _migrate_table(self, table_name: str, model_class) -> int:
        """
        迁移单个 ORM 表（从源数据库到目标数据库）

        Returns:
            成功迁移的记录数
        """
        logger.info(f"📦 [迁移] {table_name}...")

        try:
            # 从源数据库读取数据
            async with self.source_session_factory() as source_session:
                result = await source_session.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()

                if not rows:
                    logger.info(f"  └─ 表为空，跳过")
                    return 0

                columns = list(result.keys())
                logger.info(f"  ├─ 找到 {len(rows)} 条记录")
                logger.info(f"  ├─ 字段: {', '.join(columns)}")

            # 获取模型字段
            model_columns = [c.name for c in model_class.__table__.columns]
            logger.debug(f"  ├─ 模型字段: {', '.join(model_columns)}")

            # 检查字段匹配度
            missing_fields = set(model_columns) - set(columns) - {'id'}
            extra_fields = set(columns) - set(model_columns)

            if missing_fields:
                logger.warning(f"  ├─ ⚠️ 缺少字段: {', '.join(missing_fields)}")
            if extra_fields:
                logger.debug(f"  ├─ 额外字段(将忽略): {', '.join(extra_fields)}")

            # 写入目标数据库
            async with self.target_session_factory() as target_session:
                success_count = 0
                error_count = 0

                for i, row in enumerate(rows):
                    try:
                        # 转换为字典
                        row_dict = dict(zip(columns, row))

                        # 智能类型转换
                        converted_data = await self._smart_convert(
                            row_dict,
                            model_class,
                            model_columns
                        )

                        # 创建对象
                        obj = model_class(**converted_data)
                        target_session.add(obj)

                        success_count += 1

                        # 每100条提交一次
                        if (i + 1) % 100 == 0:
                            await target_session.commit()
                            logger.debug(f"  ├─ 已处理 {i + 1}/{len(rows)} 条")

                    except Exception as row_error:
                        error_count += 1
                        logger.warning(f"  ├─ ⚠️ 第 {i+1} 行迁移失败: {row_error}")
                        logger.debug(f"  │   数据: {dict(zip(columns, row))}")

                # 最终提交
                await target_session.commit()

                # 输出结果
                if error_count > 0:
                    logger.warning(
                        f"  └─ ⚠️ 完成: 成功 {success_count} 条，失败 {error_count} 条"
                    )
                else:
                    logger.info(f"  └─ ✅ 成功迁移 {success_count} 条记录")

                return success_count

        except Exception as e:
            logger.error(f"  └─ ❌ 表迁移失败: {e}")
            logger.error(f"     错误类型: {type(e).__name__}")
            return 0

    async def _smart_convert(
        self,
        row_dict: Dict[str, Any],
        model_class,
        model_columns: List[str]
    ) -> Dict[str, Any]:
        """
        智能类型转换

        Args:
            row_dict: 原始行数据
            model_class: 目标模型类
            model_columns: 模型字段列表

        Returns:
            转换后的数据字典
        """
        result = {}

        for col_name in model_columns:
            if col_name not in row_dict:
                # 字段不存在，跳过或使用默认值
                continue

            value = row_dict[col_name]

            # 获取字段类型
            col_type = None
            for col in model_class.__table__.columns:
                if col.name == col_name:
                    col_type = col.type
                    break

            if value is None:
                result[col_name] = None
                continue

            # 智能类型转换
            try:
                # String 类型
                if hasattr(col_type, 'python_type') and col_type.python_type == str:
                    result[col_name] = str(value)

                # Integer 类型
                elif hasattr(col_type, 'python_type') and col_type.python_type == int:
                    if isinstance(value, float):
                        result[col_name] = int(value)
                    else:
                        result[col_name] = int(value) if value else 0

                # Float 类型
                elif hasattr(col_type, 'python_type') and col_type.python_type == float:
                    result[col_name] = float(value) if value else 0.0

                # BigInteger (时间戳)
                elif 'BIGINT' in str(col_type) or 'timestamp' in col_name.lower():
                    if isinstance(value, float):
                        result[col_name] = int(value)
                    else:
                        result[col_name] = int(value) if value else int(time.time())

                # Text/JSON (保持原样)
                else:
                    result[col_name] = value

            except Exception as convert_error:
                logger.debug(
                    f"字段 {col_name} 转换失败: {convert_error}, "
                    f"原值: {value} ({type(value)})"
                )
                result[col_name] = value

        return result

    async def _migrate_traditional_table(self, table_name: str) -> int:
        """
        迁移传统表（无 ORM 模型，从源数据库到目标数据库）

        Args:
            table_name: 表名

        Returns:
            成功迁移的记录数
        """
        logger.info(f"📦 [迁移] {table_name} (传统表)...")

        try:
            # 从源数据库读取数据
            async with self.source_session_factory() as source_session:
                result = await source_session.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()

                if not rows:
                    logger.info(f"  └─ 表为空，跳过")
                    return 0

                columns = list(result.keys())
                logger.info(f"  ├─ 找到 {len(rows)} 条记录")
                logger.info(f"  ├─ 字段: {', '.join(columns)}")

            # 获取目标表结构
            target_columns = columns  # 默认使用源表字段
            try:
                async with self.target_session_factory() as target_session:
                    check_result = await target_session.execute(
                        text(f"SELECT * FROM {table_name} LIMIT 0")
                    )
                    target_columns = list(check_result.keys())
            except Exception as e:
                logger.warning(f"  ├─ ⚠️ 目标表不存在或查询失败，将使用源表结构: {e}")

            # 检查字段匹配度
            missing_fields = set(target_columns) - set(columns) - {'id'}
            extra_fields = set(columns) - set(target_columns)

            if missing_fields:
                logger.warning(f"  ├─ ⚠️ 缺少字段: {', '.join(missing_fields)}")
            if extra_fields:
                logger.debug(f"  ├─ 额外字段(将忽略): {', '.join(extra_fields)}")

            # 使用目标表实际存在的字段
            valid_columns = [col for col in columns if col in target_columns or col == 'id']

            # 根据目标数据库类型选择占位符
            is_mysql = 'mysql' in self.target_db_url.lower()
            placeholder = '%s' if is_mysql else '?'

            # 构建插入语句
            insert_columns = ', '.join(valid_columns)
            insert_placeholders = ', '.join([placeholder] * len(valid_columns))
            insert_sql = f"INSERT INTO {table_name} ({insert_columns}) VALUES ({insert_placeholders})"

            # 写入目标数据库
            async with self.target_session_factory() as target_session:
                success_count = 0
                error_count = 0

                for i, row in enumerate(rows):
                    try:
                        # 转换为字典
                        row_dict = dict(zip(columns, row))

                        # 只选择有效字段的值
                        values = [row_dict[col] for col in valid_columns]

                        # 执行插入 - 使用字典参数而不是列表
                        # 为每个占位符创建一个参数名
                        param_names = [f'param_{j}' for j in range(len(valid_columns))]
                        param_dict = dict(zip(param_names, values))

                        # 根据数据库类型构建SQL
                        if is_mysql:
                            # MySQL: 使用 REPLACE INTO 避免主键冲突
                            placeholders_str = ', '.join([f':{pname}' for pname in param_names])
                            insert_sql_parameterized = f"REPLACE INTO {table_name} ({insert_columns}) VALUES ({placeholders_str})"
                        else:
                            # SQLite: 使用 REPLACE INTO 避免主键冲突
                            placeholders_str = ', '.join([f':{pname}' for pname in param_names])
                            insert_sql_parameterized = f"REPLACE INTO {table_name} ({insert_columns}) VALUES ({placeholders_str})"

                        await target_session.execute(text(insert_sql_parameterized), param_dict)
                        success_count += 1

                        # 每100条提交一次
                        if (i + 1) % 100 == 0:
                            await target_session.commit()
                            logger.debug(f"  ├─ 已处理 {i + 1}/{len(rows)} 条")

                    except Exception as row_error:
                        error_count += 1
                        logger.warning(f"  ├─ ⚠️ 第 {i+1} 行迁移失败: {row_error}")
                        logger.debug(f"  │   数据: {dict(zip(columns, row))}")

                # 最终提交
                await target_session.commit()

                # 输出结果
                if error_count > 0:
                    logger.warning(
                        f"  └─ ⚠️ 完成: 成功 {success_count} 条，失败 {error_count} 条"
                    )
                else:
                    logger.info(f"  └─ ✅ 成功迁移 {success_count} 条记录")

                return success_count

        except Exception as e:
            logger.error(f"  └─ ❌ 表迁移失败: {e}")
            logger.error(f"     错误类型: {type(e).__name__}")
            return 0

    async def _verify_migration(self):
        """验证目标数据库迁移数据完整性"""
        logger.info("✅ [步骤 5/5] 验证数据完整性...")

        async with self.target_session_factory() as session:
            # 验证 ORM 表
            for table_name in self.table_models.keys():
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    )
                    count = result.scalar()

                    if count > 0:
                        logger.info(f"  ├─ {table_name}: {count} 条记录")
                    else:
                        logger.debug(f"  ├─ {table_name}: 空表")

                except Exception as e:
                    logger.error(f"  ├─ {table_name}: 验证失败 - {e}")

            # 验证传统表
            for table_name in self.traditional_tables:
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    )
                    count = result.scalar()

                    if count > 0:
                        logger.info(f"  ├─ {table_name}: {count} 条记录")
                    else:
                        logger.debug(f"  ├─ {table_name}: 空表")

                except Exception as e:
                    logger.debug(f"  ├─ {table_name}: 表不存在或验证失败")

        logger.info("  └─ 验证完成")

    async def close(self):
        """关闭数据库连接"""
        if self.source_engine:
            await self.source_engine.dispose()
        if self.target_engine and self.target_engine != self.source_engine:
            await self.target_engine.dispose()
        logger.info("✅ [数据迁移] 数据库连接已关闭")


# ============================================================
# 便捷函数
# ============================================================

async def auto_migrate(source_db_url: str, target_db_url: str = None):
    """
    自动迁移数据库

    Args:
        source_db_url: 源数据库 URL
        target_db_url: 目标数据库 URL (如果为 None，则使用源数据库，用于in-place迁移)

    Examples:
        # In-place 迁移 (单个数据库)
        await auto_migrate('./data/database.db')

        # 跨数据库迁移 (SQLite → MySQL)
        await auto_migrate(
            './data/database.db',
            'mysql+aiomysql://user:pass@localhost/dbname'
        )
    """
    migrator = SmartDatabaseMigrator(source_db_url, target_db_url)

    try:
        await migrator.migrate_all()
    finally:
        await migrator.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python migration_tool_v2.py <source_db_url> [target_db_url]")
        print("\n示例:")
        print("  # In-place 迁移")
        print("  python migration_tool_v2.py ./data/database.db")
        print("\n  # 跨数据库迁移 (SQLite → MySQL)")
        print("  python migration_tool_v2.py ./data/database.db mysql+aiomysql://user:pass@localhost/dbname")
        sys.exit(1)

    source_url = sys.argv[1]
    target_url = sys.argv[2] if len(sys.argv) > 2 else None

    asyncio.run(auto_migrate(source_url, target_url))
