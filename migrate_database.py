#!/usr/bin/env python3
"""
数据库迁移工具
支持 SQLite ↔ MySQL 双向迁移
"""

import asyncio
import aiosqlite
import aiomysql
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class DatabaseMigrator:
    """数据库迁移工具"""

    # 需要迁移的表列表（按依赖顺序）
    TABLES = [
        'raw_messages',
        'bot_messages',
        'filtered_messages',
        'persona_update_records',
        'social_relations',
        'user_affection',
        'expression_patterns',
        'language_style_patterns',
        'topic_summaries',
        'learning_batches',
        'reinforcement_learning_results',
        'style_learning_records',
        'style_learning_reviews',
        'persona_fusion_history',
        'persona_update_reviews',
        'jargon',
    ]

    def __init__(self, source_type: str, target_type: str, config: Dict[str, Any]):
        """
        Args:
            source_type: 源数据库类型 ('sqlite' 或 'mysql')
            target_type: 目标数据库类型 ('sqlite' 或 'mysql')
            config: 数据库配置
        """
        self.source_type = source_type
        self.target_type = target_type
        self.config = config
        self.source_conn = None
        self.target_conn = None

    async def connect(self):
        """连接到源和目标数据库"""
        print(f"连接源数据库 ({self.source_type})...")
        if self.source_type == 'sqlite':
            self.source_conn = await aiosqlite.connect(self.config['sqlite_path'])
        else:
            self.source_conn = await aiomysql.connect(
                host=self.config['mysql_host'],
                port=self.config['mysql_port'],
                user=self.config['mysql_user'],
                password=self.config['mysql_password'],
                db=self.config['mysql_database']
            )

        print(f"连接目标数据库 ({self.target_type})...")
        if self.target_type == 'sqlite':
            self.target_conn = await aiosqlite.connect(self.config['sqlite_path_target'])
        else:
            self.target_conn = await aiomysql.connect(
                host=self.config['mysql_host_target'],
                port=self.config['mysql_port_target'],
                user=self.config['mysql_user_target'],
                password=self.config['mysql_password_target'],
                db=self.config['mysql_database_target']
            )

        print("✅ 数据库连接成功")

    async def close(self):
        """关闭数据库连接"""
        if self.source_conn:
            await self.source_conn.close()
        if self.target_conn:
            await self.target_conn.close()
        print("✅ 数据库连接已关闭")

    async def get_table_structure(self, table_name: str, db_type: str, conn) -> List[str]:
        """获取表结构的列名"""
        if db_type == 'sqlite':
            cursor = await conn.execute(f"PRAGMA table_info({table_name})")
            rows = await cursor.fetchall()
            return [row[1] for row in rows]  # 列名在索引1
        else:
            cursor = await conn.cursor()
            await cursor.execute(f"DESCRIBE {table_name}")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]  # 列名在索引0

    async def table_exists(self, table_name: str, db_type: str, conn) -> bool:
        """检查表是否存在"""
        try:
            if db_type == 'sqlite':
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                result = await cursor.fetchone()
                return result is not None
            else:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    (table_name,)
                )
                result = await cursor.fetchone()
                return result is not None
        except Exception as e:
            print(f"⚠️  检查表 {table_name} 失败: {e}")
            return False

    async def migrate_table(self, table_name: str, batch_size: int = 1000):
        """迁移单个表的数据"""
        print(f"\n📋 开始迁移表: {table_name}")

        # 检查源表是否存在
        if not await self.table_exists(table_name, self.source_type, self.source_conn):
            print(f"⚠️  源表 {table_name} 不存在，跳过")
            return

        # 检查目标表是否存在
        if not await self.table_exists(table_name, self.target_type, self.target_conn):
            print(f"⚠️  目标表 {table_name} 不存在，跳过")
            return

        # 获取表结构
        source_columns = await self.get_table_structure(table_name, self.source_type, self.source_conn)
        target_columns = await self.get_table_structure(table_name, self.target_type, self.target_conn)

        # 找到共同列
        common_columns = [col for col in source_columns if col in target_columns and col != 'id']

        if not common_columns:
            print(f"⚠️  表 {table_name} 没有共同列，跳过")
            return

        print(f"   共同列 ({len(common_columns)}): {', '.join(common_columns)}")

        # 读取源数据
        if self.source_type == 'sqlite':
            cursor = await self.source_conn.execute(f"SELECT {', '.join(common_columns)} FROM {table_name}")
            rows = await cursor.fetchall()
        else:
            cursor = await self.source_conn.cursor()
            await cursor.execute(f"SELECT {', '.join(common_columns)} FROM {table_name}")
            rows = await cursor.fetchall()

        total_rows = len(rows)
        print(f"   找到 {total_rows} 行数据")

        if total_rows == 0:
            print(f"✅ 表 {table_name} 没有数据，跳过")
            return

        # 准备插入语句
        placeholders = ', '.join(['?' if self.target_type == 'sqlite' else '%s'] * len(common_columns))
        insert_sql = f"INSERT INTO {table_name} ({', '.join(common_columns)}) VALUES ({placeholders})"

        # 批量插入
        migrated = 0
        for i in range(0, total_rows, batch_size):
            batch = rows[i:i + batch_size]

            try:
                if self.target_type == 'sqlite':
                    await self.target_conn.executemany(insert_sql, batch)
                    await self.target_conn.commit()
                else:
                    cursor = await self.target_conn.cursor()
                    await cursor.executemany(insert_sql, batch)
                    await self.target_conn.commit()

                migrated += len(batch)
                print(f"   进度: {migrated}/{total_rows} ({migrated*100//total_rows}%)")

            except Exception as e:
                print(f"❌ 批量插入失败: {e}")
                # 尝试逐行插入
                print(f"   尝试逐行插入...")
                for row in batch:
                    try:
                        if self.target_type == 'sqlite':
                            await self.target_conn.execute(insert_sql, row)
                            await self.target_conn.commit()
                        else:
                            cursor = await self.target_conn.cursor()
                            await cursor.execute(insert_sql, row)
                            await self.target_conn.commit()
                        migrated += 1
                    except Exception as row_error:
                        print(f"   ⚠️  跳过行（错误: {row_error}）")

                print(f"   进度: {migrated}/{total_rows} ({migrated*100//total_rows}%)")

        print(f"✅ 表 {table_name} 迁移完成: {migrated}/{total_rows} 行")

    async def migrate_all(self, tables: Optional[List[str]] = None, batch_size: int = 1000):
        """迁移所有表"""
        tables_to_migrate = tables or self.TABLES

        print(f"\n{'='*60}")
        print(f"开始数据库迁移")
        print(f"源数据库: {self.source_type}")
        print(f"目标数据库: {self.target_type}")
        print(f"要迁移的表: {len(tables_to_migrate)} 个")
        print(f"{'='*60}")

        start_time = datetime.now()

        for table_name in tables_to_migrate:
            await self.migrate_table(table_name, batch_size)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"✅ 迁移完成！")
        print(f"耗时: {duration:.2f} 秒")
        print(f"{'='*60}")


async def main():
    parser = argparse.ArgumentParser(description='数据库迁移工具 (SQLite ↔ MySQL)')
    parser.add_argument('--from', dest='source', required=True, choices=['sqlite', 'mysql'],
                       help='源数据库类型')
    parser.add_argument('--to', dest='target', required=True, choices=['sqlite', 'mysql'],
                       help='目标数据库类型')
    parser.add_argument('--sqlite-path', default='data/messages.db',
                       help='SQLite 数据库文件路径（作为源）')
    parser.add_argument('--sqlite-path-target', default='data/messages_migrated.db',
                       help='SQLite 数据库文件路径（作为目标）')
    parser.add_argument('--mysql-host', default='localhost',
                       help='MySQL 主机（作为源）')
    parser.add_argument('--mysql-port', type=int, default=3306,
                       help='MySQL 端口（作为源）')
    parser.add_argument('--mysql-user', default='root',
                       help='MySQL 用户名（作为源）')
    parser.add_argument('--mysql-password', default='',
                       help='MySQL 密码（作为源）')
    parser.add_argument('--mysql-database', default='bot_db',
                       help='MySQL 数据库名（作为源）')
    parser.add_argument('--mysql-host-target', default='localhost',
                       help='MySQL 主机（作为目标）')
    parser.add_argument('--mysql-port-target', type=int, default=3306,
                       help='MySQL 端口（作为目标）')
    parser.add_argument('--mysql-user-target', default='root',
                       help='MySQL 用户名（作为目标）')
    parser.add_argument('--mysql-password-target', default='',
                       help='MySQL 密码（作为目标）')
    parser.add_argument('--mysql-database-target', default='bot_db',
                       help='MySQL 数据库名（作为目标）')
    parser.add_argument('--tables', nargs='+',
                       help='要迁移的表（默认迁移所有表）')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='批量插入大小（默认 1000）')

    args = parser.parse_args()

    # 检查源和目标不能相同
    if args.source == args.target == 'sqlite' and args.sqlite_path == args.sqlite_path_target:
        print("❌ 错误: 源和目标 SQLite 文件不能相同")
        sys.exit(1)

    if args.source == args.target == 'mysql':
        if (args.mysql_host == args.mysql_host_target and
            args.mysql_port == args.mysql_port_target and
            args.mysql_database == args.mysql_database_target):
            print("❌ 错误: 源和目标 MySQL 数据库不能相同")
            sys.exit(1)

    config = {
        'sqlite_path': args.sqlite_path,
        'sqlite_path_target': args.sqlite_path_target,
        'mysql_host': args.mysql_host,
        'mysql_port': args.mysql_port,
        'mysql_user': args.mysql_user,
        'mysql_password': args.mysql_password,
        'mysql_database': args.mysql_database,
        'mysql_host_target': args.mysql_host_target,
        'mysql_port_target': args.mysql_port_target,
        'mysql_user_target': args.mysql_user_target,
        'mysql_password_target': args.mysql_password_target,
        'mysql_database_target': args.mysql_database_target,
    }

    migrator = DatabaseMigrator(args.source, args.target, config)

    try:
        await migrator.connect()
        await migrator.migrate_all(args.tables, args.batch_size)
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await migrator.close()


if __name__ == '__main__':
    asyncio.run(main())
