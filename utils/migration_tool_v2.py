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
    """

    def __init__(self, db_url: str):
        """
        初始化迁移工具

        Args:
            db_url: 数据库 URL (支持 SQLite 和 MySQL)
        """
        self.db_url = db_url

        # 创建引擎
        if 'sqlite' in db_url:
            if not db_url.startswith('sqlite+aiosqlite'):
                db_url = f"sqlite+aiosqlite:///{db_url.replace('sqlite:///', '')}"

        self.engine = create_async_engine(db_url, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # 表映射配置
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

        logger.info("🚀 [数据迁移] 智能迁移工具初始化完成")

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

            # 3. 逐表迁移数据
            total_migrated = 0
            for table_name, model_class in self.table_models.items():
                if table_name in existing_tables:
                    count = await self._migrate_table(table_name, model_class)
                    total_migrated += count
                else:
                    logger.info(f"[迁移] {table_name} - 不存在于旧数据库，已创建空表")

            # 4. 验证迁移
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
        logger.info("📝 [步骤 1/4] 创建/更新表结构...")

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ 表结构准备完成")

    async def _detect_existing_tables(self) -> List[str]:
        """检测现有表"""
        logger.info("🔍 [步骤 2/4] 检测现有表...")

        async with self.session_factory() as session:
            if 'sqlite' in self.db_url:
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            else:
                result = await session.execute(text("SHOW TABLES"))

            tables = [row[0] for row in result.fetchall()]

        return tables

    async def _migrate_table(self, table_name: str, model_class) -> int:
        """
        迁移单个表

        Returns:
            成功迁移的记录数
        """
        logger.info(f"📦 [迁移] {table_name}...")

        try:
            async with self.session_factory() as session:
                # 查询旧数据
                result = await session.execute(text(f"SELECT * FROM {table_name}"))
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

                # 逐行转换和插入
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
                        session.add(obj)

                        success_count += 1

                        # 每100条提交一次
                        if (i + 1) % 100 == 0:
                            await session.commit()
                            logger.debug(f"  ├─ 已处理 {i + 1}/{len(rows)} 条")

                    except Exception as row_error:
                        error_count += 1
                        logger.warning(f"  ├─ ⚠️ 第 {i+1} 行迁移失败: {row_error}")
                        logger.debug(f"  │   数据: {dict(zip(columns, row))}")

                # 最终提交
                await session.commit()

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

    async def _verify_migration(self):
        """验证迁移数据完整性"""
        logger.info("✅ [步骤 4/4] 验证数据完整性...")

        async with self.session_factory() as session:
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

        logger.info("  └─ 验证完成")

    async def close(self):
        """关闭连接"""
        await self.engine.dispose()


# ============================================================
# 便捷函数
# ============================================================

async def auto_migrate(db_url: str):
    """
    自动迁移数据库

    Args:
        db_url: 数据库 URL

    Examples:
        # SQLite
        await auto_migrate('./data/database.db')

        # MySQL
        await auto_migrate('mysql+aiomysql://user:pass@localhost/dbname')
    """
    migrator = SmartDatabaseMigrator(db_url)

    try:
        await migrator.migrate_all()
    finally:
        await migrator.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python migration_tool_v2.py <database_url>")
        print("示例: python migration_tool_v2.py ./data/database.db")
        sys.exit(1)

    db_url = sys.argv[1]
    asyncio.run(auto_migrate(db_url))
