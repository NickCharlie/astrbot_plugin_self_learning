"""
数据库表管理器
负责表的自动创建和存在性检查
"""
import asyncio
from typing import Set, Optional
from functools import wraps

from astrbot.api import logger

from ..core.database.backend_interface import IDatabaseBackend, DatabaseType
from .table_schemas import TableSchemas


class TableManager:
    """
    数据库表管理器
    负责确保表在访问前存在，如果不存在则自动创建
    """

    def __init__(self, db_backend: IDatabaseBackend):
        """
        初始化表管理器

        Args:
            db_backend: 数据库后端实例
        """
        self.db_backend = db_backend
        self._initialized_tables: Set[str] = set()
        self._table_locks: dict = {}  # 每个表一个锁，避免并发创建
        self._global_lock = asyncio.Lock()  # 全局锁用于初始化

    async def ensure_table_exists(self, table_name: str) -> bool:
        """
        确保表存在，如果不存在则自动创建

        Args:
            table_name: 表名

        Returns:
            bool: 表是否存在或创建成功
        """
        # 如果表已经初始化过，直接返回
        if table_name in self._initialized_tables:
            return True

        # 获取表级别的锁
        if table_name not in self._table_locks:
            async with self._global_lock:
                if table_name not in self._table_locks:
                    self._table_locks[table_name] = asyncio.Lock()

        # 使用表锁避免并发创建同一个表
        async with self._table_locks[table_name]:
            # 双重检查：可能其他协程已经创建了
            if table_name in self._initialized_tables:
                return True

            try:
                # 检查表是否存在
                exists = await self.db_backend.table_exists(table_name)

                if not exists:
                    logger.info(f"[TableManager] 表 {table_name} 不存在，开始创建...")
                    # 获取对应数据库类型的DDL
                    ddl = TableSchemas.get_table_ddl(table_name, self.db_backend.db_type)
                    # 创建表
                    success = await self.db_backend.create_table(table_name, ddl)

                    if success:
                        logger.info(f"[TableManager] 表 {table_name} 创建成功")
                        self._initialized_tables.add(table_name)
                        return True
                    else:
                        logger.error(f"[TableManager] 表 {table_name} 创建失败")
                        return False
                else:
                    # 表已存在，标记为已初始化
                    self._initialized_tables.add(table_name)
                    return True

            except Exception as e:
                logger.error(f"[TableManager] 确保表 {table_name} 存在时出错: {e}", exc_info=True)
                return False

    async def ensure_tables_exist(self, table_names: list) -> bool:
        """
        确保多个表存在

        Args:
            table_names: 表名列表

        Returns:
            bool: 所有表是否都存在或创建成功
        """
        results = await asyncio.gather(
            *[self.ensure_table_exists(name) for name in table_names],
            return_exceptions=True
        )

        # 检查是否所有表都创建成功
        success = all(r is True for r in results if not isinstance(r, Exception))

        # 记录失败的表
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[TableManager] 创建表 {table_names[i]} 时出现异常: {result}")
            elif result is False:
                logger.error(f"[TableManager] 创建表 {table_names[i]} 失败")

        return success

    async def initialize_all_tables(self) -> bool:
        """
        初始化所有定义的表

        Returns:
            bool: 是否所有表都初始化成功
        """
        all_tables = TableSchemas.get_all_table_names()
        logger.info(f"[TableManager] 开始初始化 {len(all_tables)} 个表...")
        success = await self.ensure_tables_exist(all_tables)

        if success:
            logger.info(f"[TableManager] 所有表初始化完成")
        else:
            logger.warning(f"[TableManager] 部分表初始化失败")

        return success

    def get_initialized_tables(self) -> Set[str]:
        """获取已初始化的表列表"""
        return self._initialized_tables.copy()

    def mark_table_initialized(self, table_name: str):
        """标记表为已初始化（用于外部创建表的情况）"""
        self._initialized_tables.add(table_name)


def ensure_table(table_name: str):
    """
    装饰器：确保表存在后再执行数据库操作

    用法:
        @ensure_table('social_relations')
        async def save_social_relation(self, ...):
            ...

    Args:
        table_name: 需要确保存在的表名
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 尝试获取 table_manager
            table_manager = None

            # 如果self是DatabaseManager实例
            if hasattr(self, 'table_manager'):
                table_manager = self.table_manager
            # 如果self有db_manager属性
            elif hasattr(self, 'db_manager') and hasattr(self.db_manager, 'table_manager'):
                table_manager = self.db_manager.table_manager

            # 确保表存在
            if table_manager:
                await table_manager.ensure_table_exists(table_name)
            else:
                logger.warning(f"[ensure_table] 无法获取 table_manager，跳过表 {table_name} 的存在性检查")

            # 执行原函数
            return await func(self, *args, **kwargs)

        return wrapper
    return decorator
