"""
Repository 基类 - 提供通用的数据库操作
使用泛型支持类型安全
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from typing import TypeVar, Generic, Type, List, Optional, Dict, Any
from astrbot.api import logger


# 泛型类型变量
T = TypeVar('T')


class BaseRepository(Generic[T]):
    """
    Repository 基类

    提供通用的 CRUD 操作:
    - get_by_id: 根据 ID 获取单条记录
    - get_all: 获取所有记录
    - create: 创建新记录
    - update: 更新记录
    - delete: 删除记录
    - count: 统计记录数

    子类可以添加特定的查询方法
    """

    def __init__(self, session: AsyncSession, model_class: Type[T]):
        """
        初始化 Repository

        Args:
            session: 异步数据库会话
            model_class: ORM 模型类
        """
        self.session = session
        self.model_class = model_class

    async def get_by_id(self, id: int) -> Optional[T]:
        """
        根据 ID 获取记录

        Args:
            id: 记录 ID

        Returns:
            Optional[T]: 记录对象，如果不存在返回 None
        """
        try:
            return await self.session.get(self.model_class, id)
        except Exception as e:
            logger.error(f"[{self.model_class.__name__}] 根据 ID 获取记录失败: {e}")
            return None

    async def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        """
        获取所有记录

        Args:
            limit: 限制返回数量
            offset: 偏移量

        Returns:
            List[T]: 记录列表
        """
        try:
            stmt = select(self.model_class)

            if offset > 0:
                stmt = stmt.offset(offset)

            if limit:
                stmt = stmt.limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[{self.model_class.__name__}] 获取所有记录失败: {e}")
            return []

    async def create(self, **kwargs) -> Optional[T]:
        """
        创建新记录

        Args:
            **kwargs: 字段名和值

        Returns:
            Optional[T]: 创建的对象
        """
        try:
            obj = self.model_class(**kwargs)
            self.session.add(obj)
            await self.session.commit()
            await self.session.refresh(obj)
            return obj

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 创建记录失败: {e}")
            return None

    async def update(self, obj: T) -> Optional[T]:
        """
        更新记录

        Args:
            obj: 要更新的对象

        Returns:
            Optional[T]: 更新后的对象
        """
        try:
            await self.session.commit()
            await self.session.refresh(obj)
            return obj

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 更新记录失败: {e}")
            return None

    async def delete(self, obj: T) -> bool:
        """
        删除记录

        Args:
            obj: 要删除的对象

        Returns:
            bool: 是否删除成功
        """
        try:
            await self.session.delete(obj)
            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 删除记录失败: {e}")
            return False

    async def delete_by_id(self, id: int) -> bool:
        """
        根据 ID 删除记录

        Args:
            id: 记录 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            stmt = delete(self.model_class).where(self.model_class.id == id)
            await self.session.execute(stmt)
            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 根据 ID 删除记录失败: {e}")
            return False

    async def count(self, **filters) -> int:
        """
        统计记录数

        Args:
            **filters: 过滤条件

        Returns:
            int: 记录数量
        """
        try:
            stmt = select(func.count()).select_from(self.model_class)

            # 应用过滤条件
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    stmt = stmt.where(getattr(self.model_class, key) == value)

            result = await self.session.execute(stmt)
            return result.scalar() or 0

        except Exception as e:
            logger.error(f"[{self.model_class.__name__}] 统计记录失败: {e}")
            return 0

    async def exists(self, **filters) -> bool:
        """
        检查记录是否存在

        Args:
            **filters: 过滤条件

        Returns:
            bool: 是否存在
        """
        count = await self.count(**filters)
        return count > 0

    async def find_one(self, **filters) -> Optional[T]:
        """
        根据条件查找单条记录

        Args:
            **filters: 过滤条件

        Returns:
            Optional[T]: 记录对象，如果不存在返回 None
        """
        try:
            stmt = select(self.model_class)

            # 应用过滤条件
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    stmt = stmt.where(getattr(self.model_class, key) == value)

            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[{self.model_class.__name__}] 查找单条记录失败: {e}")
            return None

    async def find_many(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order_by: Optional[str] = None,
        **filters
    ) -> List[T]:
        """
        根据条件查找多条记录

        Args:
            limit: 限制返回数量
            offset: 偏移量
            order_by: 排序字段名
            **filters: 过滤条件

        Returns:
            List[T]: 记录列表
        """
        try:
            stmt = select(self.model_class)

            # 应用过滤条件
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    stmt = stmt.where(getattr(self.model_class, key) == value)

            # 排序
            if order_by and hasattr(self.model_class, order_by):
                stmt = stmt.order_by(getattr(self.model_class, order_by))

            # 分页
            if offset > 0:
                stmt = stmt.offset(offset)

            if limit:
                stmt = stmt.limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[{self.model_class.__name__}] 查找多条记录失败: {e}")
            return []

    async def update_by_id(self, id: int, **kwargs) -> bool:
        """
        根据 ID 更新记录

        Args:
            id: 记录 ID
            **kwargs: 要更新的字段和值

        Returns:
            bool: 是否更新成功
        """
        try:
            stmt = update(self.model_class).where(
                self.model_class.id == id
            ).values(**kwargs)

            await self.session.execute(stmt)
            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 根据 ID 更新记录失败: {e}")
            return False

    async def bulk_create(self, records: List[Dict[str, Any]]) -> List[T]:
        """
        批量创建记录

        Args:
            records: 记录数据列表

        Returns:
            List[T]: 创建的对象列表
        """
        try:
            objects = [self.model_class(**record) for record in records]
            self.session.add_all(objects)
            await self.session.commit()

            # 刷新所有对象
            for obj in objects:
                await self.session.refresh(obj)

            return objects

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 批量创建记录失败: {e}")
            return []

    async def bulk_delete(self, **filters) -> int:
        """
        批量删除记录

        Args:
            **filters: 过滤条件

        Returns:
            int: 删除的记录数
        """
        try:
            stmt = delete(self.model_class)

            # 应用过滤条件
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    stmt = stmt.where(getattr(self.model_class, key) == value)

            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[{self.model_class.__name__}] 批量删除记录失败: {e}")
            return 0
