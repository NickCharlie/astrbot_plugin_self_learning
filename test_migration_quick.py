#!/usr/bin/env python3
"""
快速测试脚本 - 验证数据库迁移系统
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_migration_detection():
    """测试迁移检测逻辑"""
    from utils.migration_tool import DatabaseMigrationTool

    # 使用项目中配置的数据库路径
    db_path = "./data/database.db"

    print("=" * 70)
    print("🧪 数据库迁移检测测试")
    print("=" * 70)
    print(f"数据库路径: {db_path}")
    print(f"文件存在: {os.path.exists(db_path)}")
    print()

    # 创建迁移工具
    migrator = DatabaseMigrationTool(f"sqlite:///{db_path}", db_type='sqlite')

    try:
        # 检查是否需要迁移
        print("🔍 检查是否需要迁移...")
        need_migration = await migrator.check_need_migration()

        print()
        print("=" * 70)
        if need_migration:
            print("✅ 检测结果: 需要执行迁移")
            print()
            print("下一步:")
            print("1. 系统会自动备份现有数据库")
            print("2. 迁移 persona_update_reviews, style_learning_reviews, expression_patterns")
            print("3. 创建新表结构")
        else:
            print("✅ 检测结果: 无需迁移")
            print()
            if not os.path.exists(db_path):
                print("原因: 数据库文件不存在（全新安装）")
            else:
                print("原因: 数据库已是最新版本或已迁移")
        print("=" * 70)

    except Exception as e:
        print(f"❌ 检测失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await migrator.close()


async def test_schema_validator():
    """测试表结构验证器"""
    from utils.schema_validator import SchemaValidator

    db_path = "./data/database.db"

    print()
    print("=" * 70)
    print("🧪 表结构验证测试")
    print("=" * 70)

    if not os.path.exists(db_path):
        print("⏭️  数据库文件不存在，跳过表结构验证测试")
        print("=" * 70)
        return

    validator = SchemaValidator(f"sqlite:///{db_path}", db_type='sqlite')

    try:
        print("🔍 验证表结构（不自动修复）...")
        diffs = await validator.validate_all_tables(auto_fix=False)

        print()
        print("=" * 70)
        if diffs:
            print(f"⚠️  发现 {len(diffs)} 个表存在结构差异")
            print()
            print("建议: 启动插件时会自动修复这些差异")
        else:
            print("✅ 所有表结构验证通过")
        print("=" * 70)

    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await validator.close()


async def test_database_factory():
    """测试数据库工厂"""
    print()
    print("=" * 70)
    print("🧪 数据库管理器工厂测试")
    print("=" * 70)

    try:
        from services.database_factory import create_database_manager
        from config import PluginConfig

        # 创建一个模拟配置
        class MockConfig:
            sqlite_path = "./data/database.db"
            mysql_host = "localhost"
            mysql_port = 3306
            mysql_user = "root"
            mysql_password = ""
            mysql_database = "test"
            use_mysql = False

        config = MockConfig()

        print("🔧 创建数据库管理器...")
        db_manager = create_database_manager(config)

        print(f"✅ 成功创建: {db_manager.__class__.__name__}")
        print(f"   类型: {type(db_manager)}")
        print()

        # 检查是否是 SQLAlchemy 版本
        from services.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
        if isinstance(db_manager, SQLAlchemyDatabaseManager):
            print("✅ 确认使用 SQLAlchemy 数据库管理器")
        else:
            print("❌ 警告: 不是 SQLAlchemy 数据库管理器!")

        print("=" * 70)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主测试函数"""
    print()
    print("🚀 开始数据库迁移系统测试")
    print()

    # 测试 1: 数据库工厂
    await test_database_factory()

    # 测试 2: 迁移检测
    await test_migration_detection()

    # 测试 3: 表结构验证
    await test_schema_validator()

    print()
    print("=" * 70)
    print("✅ 所有测试完成")
    print("=" * 70)
    print()
    print("下一步:")
    print("1. 如果要测试全新安装: 备份并删除 data/database.db")
    print("2. 如果要测试迁移: 准备旧版本数据库文件")
    print("3. 启动插件，观察日志输出")
    print()


if __name__ == "__main__":
    asyncio.run(main())
