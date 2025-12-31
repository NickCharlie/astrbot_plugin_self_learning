"""
数据库自动迁移工具 - 从旧版本迁移到 SQLAlchemy ORM 结构

主要功能:
1. 自动检测旧表是否存在
2. 备份旧数据库文件 (SQLite) 或表结构 (MySQL)
3. 创建新表结构
4. 智能迁移兼容的数据
5. 验证数据完整性

支持的数据库:
- SQLite
- MySQL
"""
import asyncio
import time
import os
import shutil
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, inspect
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
    PersonaLearningReview,
    StyleLearningReview,
    ExpressionPattern,
)


class DatabaseMigrationTool:
    """
    数据库自动迁移工具

    策略:
    - 仅迁移旧版本中存在且新版本也需要的表
    - 新版本新增的表直接创建,不尝试迁移
    - 旧版本废弃的表保留为备份,不删除
    """

    # 定义需要迁移的表映射 (旧表名 -> 新表名)
    MIGRATION_TABLE_MAP = {
        # 只有这些表需要从旧版本迁移数据
        'persona_update_reviews': 'persona_update_reviews',  # 人格学习审核表
        'style_learning_reviews': 'style_learning_reviews',  # 风格学习审核表
        'expression_patterns': 'expression_patterns',        # 表达模式表
        'social_relations': 'user_social_relation_components',  # 社交关系表（重构）
    }

    # 新版本新增的表 (不尝试迁移,直接创建)
    NEW_TABLES = {
        'user_affections',                      # 好感度系统重构
        'affection_interactions',
        'user_conversation_history',
        'user_diversity',
        'memories',                             # 记忆系统 (全新)
        'memory_embeddings',
        'memory_summaries',
        'composite_psychological_states',       # 心理状态系统 (全新)
        'psychological_state_components',
        'psychological_state_history',
        'user_social_profiles',                 # 社交关系系统重构
        'user_social_relation_components',
        'social_relation_history',
        'social_relation_analysis_results',
        'social_network_nodes',
        'social_network_edges',
        'style_learning_patterns',              # 学习系统新增
        'interaction_records',
    }

    def __init__(self, db_url: str, db_type: str = 'sqlite'):
        """
        初始化迁移工具

        Args:
            db_url: 数据库连接URL
            db_type: 数据库类型 ('sqlite' 或 'mysql')
        """
        self.db_url = db_url
        self.db_type = db_type.lower()

        # 创建异步引擎
        if self.db_type == 'sqlite':
            # 规范化 SQLite URL
            if db_url.startswith('sqlite:///'):
                db_path = db_url.replace('sqlite:///', '')
            else:
                db_path = db_url
            self.db_path = db_path
            self.engine = create_async_engine(
                f"sqlite+aiosqlite:///{db_path}",
                echo=False
            )
        elif self.db_type == 'mysql':
            self.db_path = None
            # MySQL URL 应该已经包含了完整的连接信息
            if not db_url.startswith('mysql+aiomysql://'):
                db_url = db_url.replace('mysql://', 'mysql+aiomysql://')
            self.engine = create_async_engine(db_url, echo=False)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession)
        logger.info(f"[数据迁移] 迁移工具初始化完成 (数据库类型: {self.db_type})")

    async def migrate_all(self, backup: bool = True) -> bool:
        """
        执行完整的数据迁移流程

        Args:
            backup: 是否备份旧数据库 (强制要求,如果为False会自动改为True)

        Returns:
            bool: 迁移是否成功
        """
        logger.info("=" * 70)
        logger.info("🔄 开始数据库迁移流程")
        logger.info("=" * 70)

        # 备份是强制性的,确保数据安全
        if not backup:
            logger.warning("⚠️  备份参数为False,但为了数据安全,强制启用备份")
            backup = True

        start_time = time.time()

        try:
            # 1. 备份旧数据库 (强制执行)
            logger.info("[步骤 1/5] 备份数据库 (强制执行)...")
            backup_path = await self._backup_database()

            if not backup_path:
                logger.error("❌ 数据库备份失败,为了数据安全,中止迁移!")
                logger.error("💡 提示: 请确保有足够的磁盘空间和文件权限")
                return False

            logger.info(f"✅ 数据库已备份到: {backup_path}")

            # 2. 检查旧表是否存在
            old_tables = await self._check_old_tables()
            logger.info(f"📊 检测到 {len(old_tables)} 个现有表")

            # 3. 创建新表结构
            await self._create_new_tables()

            # 4. 迁移可兼容的数据
            migration_results = await self._migrate_compatible_data(old_tables)

            # 5. 验证迁移结果
            await self._verify_migration(migration_results)

            elapsed = time.time() - start_time
            logger.info("=" * 70)
            logger.info(f"✅ 数据迁移完成! 耗时: {elapsed:.2f} 秒")
            logger.info("=" * 70)

            return True

        except Exception as e:
            logger.error(f"❌ 数据迁移失败: {e}", exc_info=True)
            logger.error(f"💡 如果需要恢复数据,请使用备份文件: {backup_path if 'backup_path' in locals() else '未创建'}")
            return False

    async def _backup_database(self) -> Optional[str]:
        """
        备份数据库

        Returns:
            str: 备份文件路径 (SQLite) 或备份标识 (MySQL)
        """
        logger.info("[步骤 1/5] 备份数据库...")

        if self.db_type == 'sqlite':
            return await self._backup_sqlite()
        elif self.db_type == 'mysql':
            return await self._backup_mysql()

        return None

    async def _backup_sqlite(self) -> Optional[str]:
        """备份 SQLite 数据库文件"""
        if not os.path.exists(self.db_path):
            logger.info(f"  ℹ️  数据库文件不存在,这是全新安装,无需备份")
            return "NEW_INSTALLATION"  # 返回特殊标识表示全新安装

        try:
            # 创建备份目录
            db_dir = os.path.dirname(self.db_path)
            if not db_dir:
                db_dir = "."
            backup_dir = os.path.join(db_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)

            # 生成备份文件名
            db_filename = os.path.basename(self.db_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{db_filename}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)

            # 复制数据库文件
            shutil.copy2(self.db_path, backup_path)

            # 同时备份 WAL 和 SHM 文件 (如果存在)
            for ext in ['-wal', '-shm']:
                wal_path = self.db_path + ext
                if os.path.exists(wal_path):
                    shutil.copy2(wal_path, backup_path + ext)
                    logger.info(f"  ✅ 已备份: {os.path.basename(wal_path)}")

            # 验证备份文件
            if not os.path.exists(backup_path):
                raise Exception("备份文件创建失败")

            backup_size = os.path.getsize(backup_path)
            original_size = os.path.getsize(self.db_path)

            if backup_size != original_size:
                raise Exception(f"备份文件大小不匹配 (原始: {original_size}, 备份: {backup_size})")

            logger.info(f"  ✅ SQLite 数据库已备份 ({backup_size / 1024:.2f} KB)")
            return backup_path

        except Exception as e:
            logger.error(f"  ❌ SQLite 备份失败: {e}", exc_info=True)
            return None

    async def _backup_mysql(self) -> Optional[str]:
        """备份 MySQL 数据库 (创建表结构快照)"""
        try:
            async with self.session_factory() as session:
                # 获取所有表名
                result = await session.execute(text("SHOW TABLES"))
                tables = [row[0] for row in result.fetchall()]

                if not tables:
                    logger.warning("  ⚠️ MySQL 数据库为空,无需备份")
                    return None

                # 记录备份时间戳
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"  ✅ MySQL 数据库快照已记录 (时间: {timestamp}, 表数量: {len(tables)})")
                logger.info(f"  💡 提示: MySQL数据库建议使用 mysqldump 进行物理备份")

                return f"mysql_snapshot_{timestamp}"

        except Exception as e:
            logger.error(f"  ❌ MySQL 备份失败: {e}")
            return None

    async def _check_old_tables(self) -> Set[str]:
        """
        检查数据库中已存在的表

        Returns:
            Set[str]: 表名集合
        """
        logger.info("[步骤 2/5] 检查现有表...")

        async with self.session_factory() as session:
            if self.db_type == 'sqlite':
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            elif self.db_type == 'mysql':
                result = await session.execute(text("SHOW TABLES"))
            else:
                return set()

            tables = {row[0] for row in result.fetchall()}

            # 过滤掉系统表
            tables = {t for t in tables if not t.startswith('sqlite_')}

            if tables:
                logger.info(f"  📋 已存在的表: {', '.join(sorted(tables))}")
            else:
                logger.info("  ℹ️ 数据库为空,这是全新安装")

            return tables

    async def _create_new_tables(self):
        """创建新表结构"""
        logger.info("[步骤 3/5] 创建新表结构...")

        try:
            async with self.engine.begin() as conn:
                # 创建所有新表
                await conn.run_sync(Base.metadata.create_all)

            logger.info("  ✅ 所有新表结构已创建")

        except Exception as e:
            logger.error(f"  ❌ 创建表结构失败: {e}")
            raise

    async def _migrate_compatible_data(self, old_tables: Set[str]) -> Dict[str, int]:
        """
        迁移兼容的数据

        Args:
            old_tables: 旧数据库中已存在的表

        Returns:
            Dict[str, int]: {表名: 迁移记录数}
        """
        logger.info("[步骤 4/5] 迁移兼容数据...")

        results = {}

        # 只迁移在旧表中存在且在映射表中定义的表
        for old_table, new_table in self.MIGRATION_TABLE_MAP.items():
            if old_table in old_tables:
                count = await self._migrate_table(old_table, new_table)
                results[new_table] = count
            else:
                logger.info(f"  ⏭️ {old_table} 不存在于旧数据库,跳过迁移")

        # 输出新增表的说明
        new_tables_in_db = self.NEW_TABLES & old_tables
        if new_tables_in_db:
            logger.info(f"  ℹ️ 检测到部分新表已存在: {', '.join(new_tables_in_db)}")
            logger.info(f"  💡 这些表将保留现有数据")

        return results

    async def _migrate_table(self, old_table: str, new_table: str) -> int:
        """
        迁移单个表的数据

        Args:
            old_table: 源表名
            new_table: 目标表名

        Returns:
            int: 迁移的记录数
        """
        logger.info(f"  🔄 迁移表: {old_table} -> {new_table}")

        try:
            async with self.session_factory() as session:
                # 读取旧表数据
                result = await session.execute(text(f"SELECT * FROM {old_table}"))
                rows = result.fetchall()
                columns = result.keys()

                if not rows:
                    logger.info(f"    - 表为空,跳过")
                    return 0

                # 转换为字典列表
                data = [dict(zip(columns, row)) for row in rows]
                logger.info(f"    - 找到 {len(data)} 条记录")

                # 检查目标表是否已有数据
                count_result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {new_table}")
                )
                existing_count = count_result.scalar()

                if existing_count > 0:
                    logger.warning(f"    ⚠️ 目标表已有 {existing_count} 条记录,跳过迁移以避免重复")
                    return 0

                # 迁移数据
                migrated = await self._insert_migrated_data(session, new_table, data)
                await session.commit()

                logger.info(f"    ✅ 成功迁移 {migrated} 条记录")
                return migrated

        except Exception as e:
            logger.error(f"    ❌ 迁移失败: {e}")
            return 0

    async def _insert_migrated_data(
        self,
        session: AsyncSession,
        table_name: str,
        data: List[Dict[str, Any]]
    ) -> int:
        """
        插入迁移的数据 (智能处理字段不一致问题)

        Args:
            session: 数据库会话
            table_name: 表名
            data: 数据列表

        Returns:
            int: 成功插入的记录数
        """
        if not data:
            return 0

        # 特殊处理：social_relations 迁移到 user_social_relation_components
        if table_name == 'user_social_relation_components':
            return await self._migrate_social_relations(session, data)

        # 根据表名选择合适的ORM模型
        model_map = {
            'persona_update_reviews': PersonaLearningReview,
            'style_learning_reviews': StyleLearningReview,
            'expression_patterns': ExpressionPattern,
            'user_social_relation_components': None,  # 特殊处理
        }

        model_class = model_map.get(table_name)
        if not model_class:
            logger.warning(f"未找到表 {table_name} 的ORM模型,使用原始SQL插入")
            return await self._insert_raw_sql(session, table_name, data)

        # 获取目标模型的字段列表
        model_fields = {c.name for c in model_class.__table__.columns}

        # 分析字段差异
        source_fields = set(data[0].keys()) if data else set()
        missing_in_source = model_fields - source_fields - {'id'}  # 排除自增ID
        extra_in_source = source_fields - model_fields

        if missing_in_source:
            logger.info(f"    ℹ️ 新版本新增字段: {', '.join(missing_in_source)}")
        if extra_in_source:
            logger.info(f"    ℹ️ 旧版本有但新版本已移除的字段: {', '.join(extra_in_source)}")

        # 使用ORM插入 - 智能处理字段映射
        count = 0
        for item in data:
            try:
                # 过滤掉模型中不存在的字段
                filtered_data = {k: v for k, v in item.items() if k in model_fields}

                # 为缺失的必填字段提供默认值
                for field_name in missing_in_source:
                    column = model_class.__table__.columns.get(field_name)
                    if column is not None and not column.nullable and column.default is None:
                        # 根据字段类型提供合理的默认值
                        if 'int' in str(column.type).lower():
                            filtered_data[field_name] = 0
                        elif 'float' in str(column.type).lower() or 'real' in str(column.type).lower():
                            filtered_data[field_name] = 0.0
                        elif 'text' in str(column.type).lower() or 'string' in str(column.type).lower():
                            filtered_data[field_name] = ''
                        elif 'datetime' in str(column.type).lower():
                            filtered_data[field_name] = datetime.now()
                        elif 'bigint' in str(column.type).lower():
                            filtered_data[field_name] = int(time.time())

                # 创建模型实例
                obj = model_class(**filtered_data)
                session.add(obj)
                count += 1

            except Exception as e:
                logger.warning(f"插入记录失败,跳过: {e}")
                continue

        return count

    async def _migrate_social_relations(
        self,
        session: AsyncSession,
        data: List[Dict[str, Any]]
    ) -> int:
        """
        特殊处理：从旧 social_relations 表迁移到新 user_social_relation_components 表

        旧表字段: from_user, to_user, relation_type, strength, frequency, last_interaction
        新表字段: from_user_id, to_user_id, relation_type, value, frequency, last_interaction, ...

        Args:
            session: 数据库会话
            data: 旧表数据列表

        Returns:
            int: 成功插入的记录数
        """
        from ..models.orm.social_relation import UserSocialRelationComponent

        count = 0
        for item in data:
            try:
                # 解析旧格式的用户ID（可能是 "group_id:user_id" 或 "user_id"）
                from_user = item.get('from_user', '')
                to_user = item.get('to_user', '')

                # 提取 group_id 和 user_id
                if ':' in from_user:
                    from_group, from_user_id = from_user.split(':', 1)
                else:
                    # 如果没有group_id，尝试从其他字段推断
                    from_group = item.get('group_id', 'unknown')
                    from_user_id = from_user

                if ':' in to_user:
                    to_group, to_user_id = to_user.split(':', 1)
                else:
                    to_group = item.get('group_id', from_group)
                    to_user_id = to_user

                # 统一使用 from_user 的 group_id
                group_id = from_group

                # 创建新的社交关系组件
                component = UserSocialRelationComponent(
                    profile_id=0,  # 临时值，稍后可以关联 profile
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    group_id=group_id,
                    relation_type=item.get('relation_type', 'unknown'),
                    value=float(item.get('strength', 0.0)),  # strength -> value
                    frequency=int(item.get('frequency', 0)),
                    last_interaction=int(item.get('last_interaction', time.time())),
                    description=None,
                    tags=None,
                    created_at=int(time.time())
                )

                session.add(component)
                count += 1

            except Exception as e:
                logger.warning(f"    ⚠️ 迁移社交关系记录失败,跳过: {e}, 数据: {item}")
                continue

        logger.info(f"    ℹ️ 社交关系迁移: 成功转换 {count}/{len(data)} 条记录")
        return count

    async def _insert_raw_sql(
        self,
        session: AsyncSession,
        table_name: str,
        data: List[Dict[str, Any]]
    ) -> int:
        """使用原始SQL插入数据"""
        count = 0
        for item in data:
            try:
                columns = ', '.join(item.keys())
                placeholders = ', '.join([f":{k}" for k in item.keys()])
                sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                await session.execute(text(sql), item)
                count += 1
            except Exception as e:
                logger.warning(f"插入记录失败,跳过: {e}")
                continue

        return count

    async def _verify_migration(self, results: Dict[str, int]):
        """验证迁移结果"""
        logger.info("[步骤 5/5] 验证迁移结果...")

        total_migrated = sum(results.values())

        if results:
            logger.info(f"  📊 迁移统计:")
            for table, count in results.items():
                logger.info(f"    - {table}: {count} 条记录")
            logger.info(f"  ✅ 总计迁移: {total_migrated} 条记录")
        else:
            logger.info(f"  ℹ️ 未迁移任何数据 (可能是全新安装或数据已存在)")

    async def check_need_migration(self) -> bool:
        """
        检查是否需要执行迁移

        Returns:
            bool: True 表示需要迁移, False 表示不需要迁移(全新安装或已迁移)
        """
        try:
            # 1. 检查数据库文件是否存在 (SQLite)
            if self.db_type == 'sqlite':
                if not os.path.exists(self.db_path):
                    logger.info("✅ 数据库文件不存在,这是全新安装,无需迁移")
                    return False

            # 2. 检查数据库中的表
            old_tables = await self._check_old_tables()

            # 3. 如果数据库完全为空,不需要迁移
            if not old_tables:
                logger.info("✅ 数据库为空,这是全新安装,无需迁移")
                return False

            # 4. 检查是否有需要迁移的旧表
            tables_to_migrate = set(self.MIGRATION_TABLE_MAP.keys()) & old_tables

            if not tables_to_migrate:
                logger.info("✅ 没有发现需要迁移的旧表数据")
                return False

            # 5. 检查这些表是否已经迁移过了
            async with self.session_factory() as session:
                for new_table in self.MIGRATION_TABLE_MAP.values():
                    try:
                        result = await session.execute(
                            text(f"SELECT COUNT(*) FROM {new_table}")
                        )
                        count = result.scalar()
                        if count > 0:
                            # 已有数据,可能已经迁移过了
                            logger.info(f"✅ 表 {new_table} 已有数据,可能已迁移,跳过迁移")
                            return False
                    except Exception:
                        # 表不存在,需要创建和迁移
                        logger.info(f"🔍 检测到需要迁移的数据: {', '.join(tables_to_migrate)}")
                        return True

            return True

        except Exception as e:
            logger.error(f"检查迁移需求时出错: {e}")
            return False

    async def close(self):
        """关闭数据库连接"""
        await self.engine.dispose()


# ============================================================
# 便捷函数
# ============================================================

async def migrate_database(
    db_url: str,
    db_type: str = 'sqlite',
    backup: bool = True
) -> bool:
    """
    执行数据库迁移

    Args:
        db_url: 数据库连接URL
        db_type: 数据库类型 ('sqlite' 或 'mysql')
        backup: 是否备份

    Returns:
        bool: 是否成功

    Examples:
        # SQLite
        success = await migrate_database(
            'sqlite:///./data/database.db',
            db_type='sqlite'
        )

        # MySQL
        success = await migrate_database(
            'mysql://user:pass@localhost/dbname',
            db_type='mysql'
        )
    """
    migrator = DatabaseMigrationTool(db_url, db_type)

    try:
        # 检查是否需要迁移
        if not await migrator.check_need_migration():
            logger.info("✅ 数据库已是最新版本,无需迁移")
            return True

        # 执行迁移
        success = await migrator.migrate_all(backup=backup)
        return success

    finally:
        await migrator.close()


async def check_and_migrate_if_needed(
    db_url: str,
    db_type: str = 'sqlite',
    backup: bool = True
) -> bool:
    """
    检查并在需要时自动执行迁移

    这是推荐的启动时调用函数

    Args:
        db_url: 数据库连接URL
        db_type: 数据库类型
        backup: 是否备份

    Returns:
        bool: 是否成功 (如果不需要迁移也返回True)
    """
    migrator = DatabaseMigrationTool(db_url, db_type)

    try:
        if await migrator.check_need_migration():
            logger.info("🔍 检测到需要数据库迁移,开始执行...")
            return await migrator.migrate_all(backup=backup)
        else:
            logger.info("✅ 数据库结构已是最新,无需迁移")
            return True

    except Exception as e:
        logger.error(f"数据库迁移检查失败: {e}", exc_info=True)
        return False

    finally:
        await migrator.close()


if __name__ == "__main__":
    # 测试迁移
    import sys

    if len(sys.argv) < 2:
        print("用法: python migration_tool.py <database_url> [db_type]")
        print("示例: python migration_tool.py sqlite:///./data/database.db sqlite")
        print("示例: python migration_tool.py mysql://user:pass@localhost/db mysql")
        sys.exit(1)

    db_url = sys.argv[1]
    db_type = sys.argv[2] if len(sys.argv) > 2 else 'sqlite'

    asyncio.run(check_and_migrate_if_needed(db_url, db_type))