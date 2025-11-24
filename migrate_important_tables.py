#!/usr/bin/env python3
"""
快速迁移重要表工具
只迁移 expression_patterns 表到 MySQL
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.database import DatabaseConfig, DatabaseType, SQLiteBackend, MySQLBackend, DatabaseMigrator
from astrbot.api import logger


async def migrate_important_tables():
    """迁移重要表到 MySQL"""

    # 配置（请根据实际情况修改）
    SQLITE_PATH = "data/messages.db"
    MYSQL_CONFIG = {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': '',  # 请填写密码
        'database': 'astrbot_self_learning',
        'charset': 'utf8mb4'
    }

    # 要迁移的重要表
    IMPORTANT_TABLES = ['expression_patterns']

    print("=" * 60)
    print("开始迁移重要表到 MySQL")
    print(f"源: SQLite ({SQLITE_PATH})")
    print(f"目标: MySQL ({MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']})")
    print(f"表: {', '.join(IMPORTANT_TABLES)}")
    print("=" * 60)
    print()

    # 创建 SQLite 后端
    sqlite_config = DatabaseConfig(
        db_type=DatabaseType.SQLITE,
        sqlite_path=SQLITE_PATH
    )
    sqlite_backend = SQLiteBackend(sqlite_config)

    # 创建 MySQL 后端
    mysql_config = DatabaseConfig(
        db_type=DatabaseType.MYSQL,
        mysql_host=MYSQL_CONFIG['host'],
        mysql_port=MYSQL_CONFIG['port'],
        mysql_user=MYSQL_CONFIG['user'],
        mysql_password=MYSQL_CONFIG['password'],
        mysql_database=MYSQL_CONFIG['database'],
        mysql_charset=MYSQL_CONFIG['charset']
    )
    mysql_backend = MySQLBackend(mysql_config)

    try:
        # 初始化数据库连接
        print("连接 SQLite 数据库...")
        if not await sqlite_backend.initialize():
            print("❌ SQLite 初始化失败")
            return

        print("连接 MySQL 数据库...")
        if not await mysql_backend.initialize():
            print("❌ MySQL 初始化失败")
            return

        print("✅ 数据库连接成功\n")

        # 创建迁移器（启用 REPLACE INTO 以处理主键冲突）
        migrator = DatabaseMigrator(
            source_backend=sqlite_backend,
            target_backend=mysql_backend,
            use_replace=True  # 使用 REPLACE INTO 自动处理冲突
        )

        # 迁移每个表
        total_rows = 0
        for table_name in IMPORTANT_TABLES:
            print(f"\n📋 迁移表: {table_name}")
            print("-" * 40)

            result = await migrator.migrate_table(table_name)

            if result['success']:
                rows = result['rows_migrated']
                total_rows += rows
                print(f"✅ 成功: {rows} 行")
            else:
                print(f"❌ 失败: {result.get('error', 'Unknown error')}")

        print("\n" + "=" * 60)
        print(f"✅ 迁移完成！")
        print(f"总计迁移: {total_rows} 行")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 迁移过程中出错: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 关闭连接
        await sqlite_backend.close()
        await mysql_backend.close()
        print("\n数据库连接已关闭")


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════╗
║          快速迁移重要表工具                              ║
║                                                          ║
║  此脚本将以下表从 SQLite 迁移到 MySQL:                  ║
║  - expression_patterns (表达模式)                       ║
║                                                          ║
║  特性:                                                   ║
║  ✓ 自动处理主键冲突 (REPLACE INTO)                      ║
║  ✓ 自动转换时间戳格式                                   ║
║  ✓ 自动匹配列                                           ║
╚══════════════════════════════════════════════════════════╝
    """)

    # 检查配置
    print("⚠️  请确保已在脚本中配置正确的 MySQL 密码！")
    response = input("按 Enter 继续，或 Ctrl+C 取消: ")

    asyncio.run(migrate_important_tables())
