#!/usr/bin/env python3
"""
从 ORM 模型生成 MySQL 建表 SQL 脚本

使用方法:
    python scripts/generate_mysql_schema.py

生成的 SQL 文件位于: scripts/mysql_schema.sql
可以直接在 MySQL 中执行此文件创建所有表
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable
from models.orm import Base


def generate_mysql_schema(output_file: str = "scripts/mysql_schema.sql"):
    """
    生成 MySQL 建表 SQL 脚本

    Args:
        output_file: 输出文件路径
    """
    # 创建一个临时的 MySQL engine（不需要真实连接）
    engine = create_engine(
        "mysql+pymysql://user:pass@localhost/dummy",
        strategy='mock',
        executor=lambda sql, *_: None
    )

    # 生成建表语句
    sql_statements = []

    # 添加数据库创建语句
    sql_statements.append("-- =====================================================")
    sql_statements.append("-- AstrBot Self Learning Plugin - MySQL Schema")
    sql_statements.append("-- 从 SQLAlchemy ORM 模型自动生成")
    sql_statements.append("-- =====================================================")
    sql_statements.append("")
    sql_statements.append("-- 创建数据库（如果不存在）")
    sql_statements.append("CREATE DATABASE IF NOT EXISTS astrbot_self_learning DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    sql_statements.append("USE astrbot_self_learning;")
    sql_statements.append("")

    # 按表名排序，确保依赖关系正确
    tables = sorted(Base.metadata.tables.values(), key=lambda t: t.name)

    for table in tables:
        # 生成 CREATE TABLE 语句
        create_table_sql = str(CreateTable(table).compile(engine))

        # 替换引擎为 InnoDB
        if "ENGINE=" not in create_table_sql:
            create_table_sql = create_table_sql.rstrip() + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

        sql_statements.append(f"-- 表: {table.name}")
        sql_statements.append(f"DROP TABLE IF EXISTS `{table.name}`;")
        sql_statements.append(create_table_sql + ";")
        sql_statements.append("")

    # 写入文件
    output_path = os.path.join(project_root, output_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))

    print(f"✅ MySQL 建表脚本已生成: {output_path}")
    print(f"📋 包含 {len(tables)} 个表")
    print("\n表列表:")
    for table in tables:
        print(f"  - {table.name}")
    print(f"\n使用方法:")
    print(f"  mysql -h 47.121.138.217 -P 13307 -u root -p < {output_file}")


if __name__ == "__main__":
    generate_mysql_schema()
