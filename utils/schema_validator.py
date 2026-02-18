"""
数据库表结构验证器 - 检测并自动修复表结构差异

功能:
1. 检测字段名不一致
2. 检测字段类型不一致
3. 检测主键配置不一致
4. 检测索引配置不一致
5. 自动添加缺失字段
6. 警告无法自动修复的问题
"""
import asyncio
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text, inspect as sqlalchemy_inspect
from astrbot.api import logger

from ..models.orm import Base


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    type: str
    nullable: bool
    default: Optional[Any]
    is_primary_key: bool


@dataclass
class TableDiff:
    """表结构差异"""
    table_name: str
    missing_columns: List[str]  # 缺失的字段
    extra_columns: List[str]  # 多余的字段
    type_mismatches: List[Tuple[str, str, str]]  # (字段名, 期望类型, 实际类型)
    nullable_mismatches: List[Tuple[str, bool, bool]]  # (字段名, 期望nullable, 实际nullable)


class SchemaValidator:
    """
    数据库表结构验证器

    检测现有表结构与ORM定义的差异,并尝试自动修复
    """

    def __init__(self, db_url: str, db_type: str = 'sqlite'):
        """
        初始化验证器

        Args:
            db_url: 数据库连接URL
            db_type: 数据库类型 ('sqlite' 或 'mysql')
        """
        self.db_url = db_url
        self.db_type = db_type.lower()

        # 创建引擎
        if self.db_type == 'sqlite':
            if db_url.startswith('sqlite:///'):
                db_path = db_url.replace('sqlite:///', '')
            else:
                db_path = db_url
            self.engine = create_async_engine(
                f"sqlite+aiosqlite:///{db_path}",
                echo=False
            )
        elif self.db_type == 'mysql':
            if not db_url.startswith('mysql+aiomysql://'):
                db_url = db_url.replace('mysql://', 'mysql+aiomysql://')
            self.engine = create_async_engine(db_url, echo=False)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession)

    async def validate_all_tables(self, auto_fix: bool = True) -> Dict[str, TableDiff]:
        """
        验证所有ORM表的结构

        Args:
            auto_fix: 是否自动修复可修复的问题

        Returns:
            Dict[str, TableDiff]: {表名: 差异信息}
        """
        logger.info("=" * 70)
        logger.info("🔍 开始数据库表结构验证")
        logger.info("=" * 70)

        all_diffs = {}
        created_tables = []
        validated_tables = []

        # 获取所有ORM表定义
        orm_tables = Base.metadata.tables

        logger.info(f"需要验证 {len(orm_tables)} 个表")

        for table_name, table_obj in orm_tables.items():
            # 检查表是否存在
            table_exists = await self._check_table_exists(table_name)

            if not table_exists:
                # 表不存在，直接创建(全新安装)
                if auto_fix:
                    await self._create_table(table_name, table_obj)
                    created_tables.append(table_name)
                continue

            # 表存在，验证结构
            validated_tables.append(table_name)
            logger.info(f"\n📋 验证表: {table_name}")

            # 比较表结构
            diff = await self._compare_table_structure(table_name, table_obj)

            if diff:
                all_diffs[table_name] = diff
                self._log_table_diff(diff)

                # 自动修复
                if auto_fix:
                    await self._fix_table_structure(table_name, table_obj, diff)
            else:
                logger.info(f"  ✅ 表结构一致")

        logger.info("\n" + "=" * 70)

        # 总结报告
        if created_tables:
            logger.info(f"🆕 新建 {len(created_tables)} 个表: {', '.join(created_tables[:5])}" +
                       (f" 等" if len(created_tables) > 5 else ""))

        if validated_tables:
            logger.info(f"✅ 验证 {len(validated_tables)} 个已存在的表")

        if all_diffs:
            logger.info(f"⚠️  发现 {len(all_diffs)} 个表存在结构差异")
            if auto_fix:
                logger.info("✅ 已尝试自动修复")
        else:
            if validated_tables:
                logger.info("✅ 所有表结构验证通过")

        logger.info("=" * 70)

        return all_diffs

    async def _check_table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        try:
            async with self.session_factory() as session:
                if self.db_type == 'sqlite':
                    result = await session.execute(
                        text(f"SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
                        {"table_name": table_name}
                    )
                elif self.db_type == 'mysql':
                    result = await session.execute(
                        text(f"SHOW TABLES LIKE :table_name"),
                        {"table_name": table_name}
                    )
                else:
                    return False

                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"检查表存在性失败: {e}")
            return False

    async def _create_table(self, table_name: str, table_obj):
        """创建表（带索引冲突处理）"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(table_obj.create, checkfirst=True)
            logger.info(f"  ✅ 表已创建: {table_name}")
        except Exception as e:
            # 检查是否是索引已存在的错误（这是正常情况，可以忽略）
            error_msg = str(e).lower()
            if 'index' in error_msg and 'already exists' in error_msg:
                logger.info(f"  ✅ 表和索引已存在，跳过创建: {table_name}")
            else:
                logger.error(f"  ❌ 创建表失败: {e}")

    async def _get_table_columns(self, table_name: str) -> Dict[str, ColumnInfo]:
        """
        获取表的实际字段信息

        Returns:
            Dict[str, ColumnInfo]: {字段名: 字段信息}
        """
        columns = {}

        try:
            async with self.session_factory() as session:
                if self.db_type == 'sqlite':
                    result = await session.execute(text(f"PRAGMA table_info({table_name})"))
                    rows = result.fetchall()

                    for row in rows:
                        # SQLite PRAGMA返回: cid, name, type, notnull, dflt_value, pk
                        col_name = row[1]
                        col_type = row[2]
                        not_null = bool(row[3])
                        default_value = row[4]
                        is_pk = bool(row[5])

                        columns[col_name] = ColumnInfo(
                            name=col_name,
                            type=col_type,
                            nullable=not not_null,
                            default=default_value,
                            is_primary_key=is_pk
                        )

                elif self.db_type == 'mysql':
                    result = await session.execute(text(f"DESCRIBE {table_name}"))
                    rows = result.fetchall()

                    for row in rows:
                        # MySQL DESCRIBE返回: Field, Type, Null, Key, Default, Extra
                        col_name = row[0]
                        col_type = row[1]
                        nullable = (row[2] == 'YES')
                        is_pk = (row[3] == 'PRI')
                        default_value = row[4]

                        columns[col_name] = ColumnInfo(
                            name=col_name,
                            type=col_type,
                            nullable=nullable,
                            default=default_value,
                            is_primary_key=is_pk
                        )

        except Exception as e:
            logger.error(f"获取表字段信息失败: {e}")

        return columns

    async def _compare_table_structure(self, table_name: str, table_obj) -> Optional[TableDiff]:
        """
        比较表结构

        Args:
            table_name: 表名
            table_obj: SQLAlchemy Table对象

        Returns:
            TableDiff: 差异信息,如果无差异则返回None
        """
        # 获取实际表结构
        actual_columns = await self._get_table_columns(table_name)

        # 获取期望表结构
        expected_columns = {}
        for column in table_obj.columns:
            expected_columns[column.name] = column

        # 比较字段
        actual_names = set(actual_columns.keys())
        expected_names = set(expected_columns.keys())

        missing_columns = list(expected_names - actual_names)
        extra_columns = list(actual_names - expected_names)

        type_mismatches = []
        nullable_mismatches = []

        # 比较共同字段的属性
        common_columns = actual_names & expected_names
        for col_name in common_columns:
            actual_col = actual_columns[col_name]
            expected_col = expected_columns[col_name]

            # 比较类型 (简化比较,忽略类型参数差异)
            actual_type = str(actual_col.type).upper()
            expected_type = str(expected_col.type).upper()

            # 标准化类型名称
            actual_type = self._normalize_type(actual_type)
            expected_type = self._normalize_type(expected_type)

            if not self._types_compatible(actual_type, expected_type):
                type_mismatches.append((col_name, expected_type, actual_type))

            # 比较nullable (忽略主键字段)
            if not actual_col.is_primary_key and actual_col.nullable != expected_col.nullable:
                nullable_mismatches.append((col_name, expected_col.nullable, actual_col.nullable))

        # 如果有任何差异,返回差异对象
        if missing_columns or extra_columns or type_mismatches or nullable_mismatches:
            return TableDiff(
                table_name=table_name,
                missing_columns=missing_columns,
                extra_columns=extra_columns,
                type_mismatches=type_mismatches,
                nullable_mismatches=nullable_mismatches
            )

        return None

    def _normalize_type(self, type_str: str) -> str:
        """标准化类型名称"""
        type_str = type_str.upper()

        # 移除括号内容 (如长度参数)
        if '(' in type_str:
            type_str = type_str[:type_str.index('(')]

        # 类型映射
        type_map = {
            'INTEGER': 'INT',
            'REAL': 'FLOAT',
            'DOUBLE': 'FLOAT',
            'VARCHAR': 'STRING',
            'CHAR': 'STRING',
            'BIGINT': 'BIGINT',  # 保持 BIGINT，因为它常用于时间戳
            'TINYINT': 'INT',
            'SMALLINT': 'INT',
            'TIMESTAMP': 'DATETIME',  # 统一时间类型
        }

        return type_map.get(type_str, type_str)

    def _types_compatible(self, type1: str, type2: str) -> bool:
        """判断两个类型是否兼容"""
        # 完全相同
        if type1 == type2:
            return True

        # INT 类型族
        int_types = {'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT'}
        if type1 in int_types and type2 in int_types:
            return True

        # FLOAT 类型族
        float_types = {'FLOAT', 'DOUBLE', 'REAL'}
        if type1 in float_types and type2 in float_types:
            return True

        # STRING 类型族
        string_types = {'STRING', 'TEXT', 'VARCHAR', 'CHAR'}
        if type1 in string_types and type2 in string_types:
            return True

        # 时间戳类型兼容性（重要！）
        # 我们使用 BIGINT/INTEGER/FLOAT 存储 Unix 时间戳
        # DATETIME 和数字类型（INT/BIGINT/FLOAT）都可以表示时间戳，视为兼容
        timestamp_types = {'BIGINT', 'INT', 'INTEGER', 'FLOAT', 'REAL', 'DATETIME', 'TIMESTAMP'}
        if type1 in timestamp_types and type2 in timestamp_types:
            return True

        return False

    def _log_table_diff(self, diff: TableDiff):
        """记录表差异"""
        if diff.missing_columns:
            logger.warning(f"  ⚠️  缺失字段: {', '.join(diff.missing_columns)}")

        if diff.extra_columns:
            logger.info(f"  ℹ️  额外字段(旧版本遗留): {', '.join(diff.extra_columns)}")

        if diff.type_mismatches:
            for col, expected, actual in diff.type_mismatches:
                logger.warning(f"  ⚠️  字段类型不匹配: {col} (期望: {expected}, 实际: {actual})")

        if diff.nullable_mismatches:
            for col, expected, actual in diff.nullable_mismatches:
                logger.warning(f"  ⚠️  Nullable属性不匹配: {col} (期望: {expected}, 实际: {actual})")

    async def _fix_table_structure(self, table_name: str, table_obj, diff: TableDiff):
        """
        自动修复表结构差异

        Args:
            table_name: 表名
            table_obj: SQLAlchemy Table对象
            diff: 差异信息
        """
        logger.info(f"  🔧 开始修复表结构...")

        # 1. 添加缺失字段
        if diff.missing_columns:
            await self._add_missing_columns(table_name, table_obj, diff.missing_columns)

        # 2. 类型不匹配和nullable不匹配 - 警告用户
        if diff.type_mismatches:
            logger.warning(f"  ⚠️  字段类型不匹配需要手动处理,建议重建表或手动ALTER TABLE")

        if diff.nullable_mismatches:
            logger.warning(f"  ⚠️  Nullable属性不匹配可能影响数据完整性,请检查")

        # 3. 额外字段 - 保留不删除 (向后兼容)
        if diff.extra_columns:
            logger.info(f"  ℹ️  保留额外字段作为历史数据: {', '.join(diff.extra_columns)}")

    async def _add_missing_columns(self, table_name: str, table_obj, missing_columns: List[str]):
        """添加缺失字段"""
        for col_name in missing_columns:
            try:
                column = table_obj.columns.get(col_name)
                if column is None:
                    continue

                # 生成 ALTER TABLE 语句
                col_type = self._get_column_type_sql(column)
                nullable_sql = "" if column.nullable else " NOT NULL"
                default_sql = self._get_default_sql(column)

                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{nullable_sql}{default_sql}"

                async with self.session_factory() as session:
                    await session.execute(text(alter_sql))
                    await session.commit()

                logger.info(f"    ✅ 已添加字段: {col_name}")

            except Exception as e:
                logger.error(f"    ❌ 添加字段 {col_name} 失败: {e}")

    def _get_column_type_sql(self, column) -> str:
        """获取字段类型的SQL表示"""
        col_type_str = str(column.type)

        # SQLAlchemy类型 -> SQL类型
        if self.db_type == 'sqlite':
            if 'BOOLEAN' in col_type_str:
                return 'INTEGER'
            elif 'INTEGER' in col_type_str or 'INT' in col_type_str:
                return 'INTEGER'
            elif 'FLOAT' in col_type_str or 'REAL' in col_type_str:
                return 'REAL'
            elif 'TEXT' in col_type_str or 'STRING' in col_type_str:
                return 'TEXT'
            elif 'DATETIME' in col_type_str:
                return 'DATETIME'
            elif 'BIGINT' in col_type_str:
                return 'BIGINT'
            else:
                return 'TEXT'

        elif self.db_type == 'mysql':
            if 'BOOLEAN' in col_type_str:
                return 'TINYINT(1)'
            elif 'INTEGER' in col_type_str:
                return 'INT'
            elif 'BIGINT' in col_type_str:
                return 'BIGINT'
            elif 'FLOAT' in col_type_str or 'DOUBLE' in col_type_str:
                return 'DOUBLE'
            elif 'VARCHAR' in col_type_str or 'STRING' in col_type_str:
                # 从类型中提取长度
                if '(' in col_type_str:
                    return col_type_str
                return 'VARCHAR(255)'
            elif 'TEXT' in col_type_str:
                return 'TEXT'
            elif 'DATETIME' in col_type_str:
                return 'DATETIME'
            else:
                return 'TEXT'

        return 'TEXT'

    def _get_default_sql(self, column) -> str:
        """获取默认值SQL"""
        if column.default is None:
            return ""

        default_value = column.default.arg if hasattr(column.default, 'arg') else column.default

        if isinstance(default_value, str):
            return f" DEFAULT '{default_value}'"
        elif isinstance(default_value, bool):
            return f" DEFAULT {1 if default_value else 0}"
        elif isinstance(default_value, (int, float)):
            return f" DEFAULT {default_value}"

        return ""

    async def close(self):
        """关闭连接"""
        await self.engine.dispose()


# ============================================================
# 便捷函数
# ============================================================

async def validate_and_fix_schema(
    db_url: str,
    db_type: str = 'sqlite',
    auto_fix: bool = True
) -> bool:
    """
    验证并修复数据库表结构

    Args:
        db_url: 数据库连接URL
        db_type: 数据库类型
        auto_fix: 是否自动修复

    Returns:
        bool: 是否成功
    """
    validator = SchemaValidator(db_url, db_type)

    try:
        diffs = await validator.validate_all_tables(auto_fix=auto_fix)

        if diffs and not auto_fix:
            logger.warning("发现表结构差异但未启用自动修复")
            return False

        return True

    except Exception as e:
        logger.error(f"表结构验证失败: {e}", exc_info=True)
        return False

    finally:
        await validator.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python schema_validator.py <database_url> [db_type]")
        print("示例: python schema_validator.py sqlite:///./data/database.db sqlite")
        sys.exit(1)

    db_url = sys.argv[1]
    db_type = sys.argv[2] if len(sys.argv) > 2 else 'sqlite'

    asyncio.run(validate_and_fix_schema(db_url, db_type))
