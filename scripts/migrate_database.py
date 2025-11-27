#!/usr/bin/env python3
"""
数据库迁移命令行工具
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.migration_tool import migrate_database


async def main():
    print("=" * 70)
    print(" AstrBot 自学习插件 - 数据库自动迁移工具")
    print("=" * 70)
    print()

    # 检查命令行参数
    if len(sys.argv) < 2:
        print("📖 用法:")
        print(f"  python {sys.argv[0]} <database_url>")
        print()
        print("📝 示例:")
        print(f"  # SQLite")
        print(f"  python {sys.argv[0]} ./data/database.db")
        print()
        print(f"  # MySQL")
        print(f"  python {sys.argv[0]} mysql+aiomysql://user:password@localhost/dbname")
        print()
        sys.exit(1)

    db_path = sys.argv[1]

    # 处理 SQLite 路径
    if not db_path.startswith('mysql') and not db_path.startswith('sqlite'):
        # 相对路径
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        db_url = f"sqlite:///{db_path}"
    else:
        db_url = db_path

    print(f"🔗 数据库: {db_url}")
    print()

    # 确认
    confirm = input("⚠️  确认开始迁移? 这将创建新表并复制数据 (y/N): ")
    if confirm.lower() != 'y':
        print("❌ 已取消")
        sys.exit(0)

    print()
    print("=" * 70)

    # 执行迁移
    try:
        await migrate_database(db_url, backup=True)
        print()
        print("=" * 70)
        print("🎉 迁移完成!")
        print("=" * 70)
        print()
        print("📋 后续步骤:")
        print("  1. 检查迁移日志，确认数据完整性")
        print("  2. 测试应用功能是否正常")
        print("  3. 如果一切正常，可以删除旧表备份")
        print()

    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ 迁移失败: {e}")
        print("=" * 70)
        print()
        print("🔧 故障排查:")
        print("  1. 检查数据库连接是否正常")
        print("  2. 确认数据库用户有足够权限")
        print("  3. 查看完整错误日志")
        print()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
