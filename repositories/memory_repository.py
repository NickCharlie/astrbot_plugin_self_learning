"""
记忆系统相关的 Repository
"""
import time
from sqlalchemy import select, and_, or_
from typing import Optional, List
from astrbot.api import logger

from .base_repository import BaseRepository
from ..models.orm import Memory, MemoryEmbedding, MemorySummary


class MemoryRepository(BaseRepository[Memory]):
    """记忆 Repository"""

    def __init__(self, session):
        super().__init__(session, Memory)

    async def create_memory(
        self,
        group_id: str,
        user_id: str,
        content: str,
        memory_type: str,
        importance: float = 0.5,
        tags: str = "[]",
        metadata: str = "{}"
    ) -> Optional[Memory]:
        """
        创建记忆

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            content: 记忆内容
            memory_type: 记忆类型
            importance: 重要性 (0-1)
            tags: 标签 JSON
            metadata: 元数据 JSON

        Returns:
            Optional[Memory]: 记忆对象
        """
        return await self.create(
            group_id=group_id,
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            metadata=metadata,
            access_count=0,
            last_accessed_at=int(time.time()),
            created_at=int(time.time()),
            updated_at=int(time.time())
        )

    async def get_by_type(
        self,
        group_id: str,
        memory_type: str,
        limit: int = 50
    ) -> List[Memory]:
        """
        根据类型获取记忆

        Args:
            group_id: 群组 ID
            memory_type: 记忆类型
            limit: 返回数量

        Returns:
            List[Memory]: 记忆列表
        """
        try:
            stmt = select(Memory).where(
                and_(
                    Memory.group_id == group_id,
                    Memory.memory_type == memory_type
                )
            ).order_by(
                Memory.importance.desc(),
                Memory.created_at.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[MemoryRepository] 根据类型获取记忆失败: {e}")
            return []

    async def get_important_memories(
        self,
        group_id: str,
        threshold: float = 0.7,
        limit: int = 20
    ) -> List[Memory]:
        """
        获取重要记忆

        Args:
            group_id: 群组 ID
            threshold: 重要性阈值
            limit: 返回数量

        Returns:
            List[Memory]: 记忆列表
        """
        try:
            stmt = select(Memory).where(
                and_(
                    Memory.group_id == group_id,
                    Memory.importance >= threshold
                )
            ).order_by(
                Memory.importance.desc(),
                Memory.last_accessed_at.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[MemoryRepository] 获取重要记忆失败: {e}")
            return []

    async def update_access(self, memory_id: int) -> bool:
        """
        更新访问记录

        Args:
            memory_id: 记忆 ID

        Returns:
            bool: 是否更新成功
        """
        try:
            memory = await self.get_by_id(memory_id)
            if memory:
                memory.access_count += 1
                memory.last_accessed_at = int(time.time())
                await self.update(memory)
                return True
            return False

        except Exception as e:
            logger.error(f"[MemoryRepository] 更新访问记录失败: {e}")
            return False

    async def clean_old_memories(
        self,
        group_id: str,
        days: int = 30,
        importance_threshold: float = 0.3
    ) -> int:
        """
        清理旧记忆

        Args:
            group_id: 群组 ID
            days: 保留天数
            importance_threshold: 重要性阈值（低于此值的旧记忆会被删除）

        Returns:
            int: 删除的记录数
        """
        try:
            from sqlalchemy import delete

            cutoff_time = int(time.time()) - (days * 24 * 3600)

            stmt = delete(Memory).where(
                and_(
                    Memory.group_id == group_id,
                    Memory.created_at < cutoff_time,
                    Memory.importance < importance_threshold
                )
            )

            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount

        except Exception as e:
            await self.session.rollback()
            logger.error(f"[MemoryRepository] 清理旧记忆失败: {e}")
            return 0


class MemoryEmbeddingRepository(BaseRepository[MemoryEmbedding]):
    """记忆嵌入 Repository"""

    def __init__(self, session):
        super().__init__(session, MemoryEmbedding)

    async def create_embedding(
        self,
        memory_id: int,
        embedding: str,
        model_name: str = "default"
    ) -> Optional[MemoryEmbedding]:
        """
        创建记忆嵌入

        Args:
            memory_id: 记忆 ID
            embedding: 嵌入向量 JSON
            model_name: 模型名称

        Returns:
            Optional[MemoryEmbedding]: 嵌入对象
        """
        return await self.create(
            memory_id=memory_id,
            embedding=embedding,
            model_name=model_name,
            created_at=int(time.time())
        )

    async def get_by_memory(self, memory_id: int) -> Optional[MemoryEmbedding]:
        """
        根据记忆 ID 获取嵌入

        Args:
            memory_id: 记忆 ID

        Returns:
            Optional[MemoryEmbedding]: 嵌入对象
        """
        return await self.find_one(memory_id=memory_id)


class MemorySummaryRepository(BaseRepository[MemorySummary]):
    """记忆摘要 Repository"""

    def __init__(self, session):
        super().__init__(session, MemorySummary)

    async def create_summary(
        self,
        group_id: str,
        summary_type: str,
        content: str,
        time_range_start: int,
        time_range_end: int,
        memory_ids: str = "[]"
    ) -> Optional[MemorySummary]:
        """
        创建记忆摘要

        Args:
            group_id: 群组 ID
            summary_type: 摘要类型
            content: 摘要内容
            time_range_start: 时间范围开始
            time_range_end: 时间范围结束
            memory_ids: 相关记忆 ID JSON

        Returns:
            Optional[MemorySummary]: 摘要对象
        """
        return await self.create(
            group_id=group_id,
            summary_type=summary_type,
            content=content,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            memory_ids=memory_ids,
            created_at=int(time.time())
        )

    async def get_recent_summaries(
        self,
        group_id: str,
        summary_type: str = None,
        limit: int = 10
    ) -> List[MemorySummary]:
        """
        获取最近的摘要

        Args:
            group_id: 群组 ID
            summary_type: 摘要类型（可选）
            limit: 返回数量

        Returns:
            List[MemorySummary]: 摘要列表
        """
        try:
            stmt = select(MemorySummary).where(
                MemorySummary.group_id == group_id
            )

            if summary_type:
                stmt = stmt.where(MemorySummary.summary_type == summary_type)

            stmt = stmt.order_by(
                MemorySummary.created_at.desc()
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[MemorySummaryRepository] 获取摘要失败: {e}")
            return []

    async def get_by_time_range(
        self,
        group_id: str,
        start_time: int,
        end_time: int
    ) -> List[MemorySummary]:
        """
        根据时间范围获取摘要

        Args:
            group_id: 群组 ID
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            List[MemorySummary]: 摘要列表
        """
        try:
            stmt = select(MemorySummary).where(
                and_(
                    MemorySummary.group_id == group_id,
                    or_(
                        # 摘要时间范围与查询时间范围有重叠
                        and_(
                            MemorySummary.time_range_start <= end_time,
                            MemorySummary.time_range_end >= start_time
                        )
                    )
                )
            ).order_by(
                MemorySummary.time_range_start.desc()
            )

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[MemorySummaryRepository] 根据时间范围获取摘要失败: {e}")
            return []
