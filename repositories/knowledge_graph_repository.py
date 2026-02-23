"""
知识图谱 Repository — KGEntity / KGRelation / KGParagraphHash 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func, update
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.knowledge_graph import KGEntity, KGRelation, KGParagraphHash


class KnowledgeEntityRepository(BaseRepository[KGEntity]):
    """知识图谱实体 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KGEntity)

    async def save_entity(
        self,
        name: str,
        group_id: str,
        entity_type: str = 'general'
    ) -> Optional[KGEntity]:
        """
        保存实体（upsert：已存在则增加 appear_count）

        Args:
            name: 实体名称
            group_id: 群组 ID
            entity_type: 实体类型

        Returns:
            Optional[KGEntity]: 实体对象
        """
        try:
            existing = await self._find_by_name_group(name, group_id)
            if existing:
                existing.appear_count = (existing.appear_count or 0) + 1
                existing.last_active_time = time.time()
                if entity_type != 'general':
                    existing.entity_type = entity_type
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                return await self.create(
                    name=name,
                    entity_type=entity_type,
                    appear_count=1,
                    last_active_time=time.time(),
                    group_id=group_id,
                )
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[KnowledgeEntityRepository] 保存实体失败: {e}")
            return None

    async def _find_by_name_group(
        self,
        name: str,
        group_id: str
    ) -> Optional[KGEntity]:
        """按名称和群组查找实体"""
        try:
            stmt = select(KGEntity).where(and_(
                KGEntity.name == name,
                KGEntity.group_id == group_id,
            ))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def get_entities(
        self,
        group_id: str,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> List[KGEntity]:
        """
        获取群组的实体列表

        Args:
            group_id: 群组 ID
            entity_type: 实体类型过滤（可选）
            limit: 最大返回数量

        Returns:
            List[KGEntity]: 实体列表（按出现次数倒序）
        """
        try:
            stmt = select(KGEntity).where(KGEntity.group_id == group_id)
            if entity_type:
                stmt = stmt.where(KGEntity.entity_type == entity_type)
            stmt = stmt.order_by(desc(KGEntity.appear_count)).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[KnowledgeEntityRepository] 获取实体列表失败: {e}")
            return []

    async def get_entity_count(self, group_id: str) -> int:
        """
        统计群组的实体数量

        Args:
            group_id: 群组 ID

        Returns:
            int: 实体数量
        """
        try:
            stmt = select(func.count()).select_from(KGEntity).where(
                KGEntity.group_id == group_id
            )
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[KnowledgeEntityRepository] 统计实体失败: {e}")
            return 0

    async def search_entities(
        self,
        group_id: str,
        keyword: str,
        limit: int = 20
    ) -> List[KGEntity]:
        """
        搜索实体

        Args:
            group_id: 群组 ID
            keyword: 搜索关键词
            limit: 最大返回数量

        Returns:
            List[KGEntity]: 匹配的实体列表
        """
        try:
            stmt = (
                select(KGEntity)
                .where(and_(
                    KGEntity.group_id == group_id,
                    KGEntity.name.contains(keyword),
                ))
                .order_by(desc(KGEntity.appear_count))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[KnowledgeEntityRepository] 搜索实体失败: {e}")
            return []


class KnowledgeRelationRepository(BaseRepository[KGRelation]):
    """知识图谱关系 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KGRelation)

    async def save_relation(
        self,
        subject: str,
        predicate: str,
        object_: str,
        group_id: str,
        confidence: float = 1.0
    ) -> Optional[KGRelation]:
        """
        保存关系（upsert：已存在则更新 confidence）

        Args:
            subject: 主体
            predicate: 谓词
            object_: 客体
            group_id: 群组 ID
            confidence: 置信度

        Returns:
            Optional[KGRelation]: 关系对象
        """
        try:
            existing = await self._find_relation(subject, predicate, object_, group_id)
            if existing:
                existing.confidence = confidence
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                return await self.create(
                    subject=subject,
                    predicate=predicate,
                    object=object_,
                    confidence=confidence,
                    created_time=time.time(),
                    group_id=group_id,
                )
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[KnowledgeRelationRepository] 保存关系失败: {e}")
            return None

    async def _find_relation(
        self,
        subject: str,
        predicate: str,
        object_: str,
        group_id: str
    ) -> Optional[KGRelation]:
        """精确查找关系"""
        try:
            stmt = select(KGRelation).where(and_(
                KGRelation.subject == subject,
                KGRelation.predicate == predicate,
                KGRelation.object == object_,
                KGRelation.group_id == group_id,
            ))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def get_relations_by_entity(
        self,
        entity_name: str,
        group_id: str,
        limit: int = 50
    ) -> List[KGRelation]:
        """
        获取与实体相关的所有关系（实体可以是主体或客体）

        Args:
            entity_name: 实体名称
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[KGRelation]: 关系列表
        """
        try:
            stmt = (
                select(KGRelation)
                .where(and_(
                    KGRelation.group_id == group_id,
                    or_(
                        KGRelation.subject == entity_name,
                        KGRelation.object == entity_name,
                    ),
                ))
                .order_by(desc(KGRelation.confidence))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[KnowledgeRelationRepository] 获取实体关系失败: {e}")
            return []

    async def get_relation_count(self, group_id: str) -> int:
        """
        统计群组的关系数量

        Args:
            group_id: 群组 ID

        Returns:
            int: 关系数量
        """
        try:
            stmt = select(func.count()).select_from(KGRelation).where(
                KGRelation.group_id == group_id
            )
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[KnowledgeRelationRepository] 统计关系失败: {e}")
            return 0


class KnowledgeParagraphHashRepository(BaseRepository[KGParagraphHash]):
    """知识图谱段落 Hash Repository（去重用）"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KGParagraphHash)

    async def save_hash(self, hash_value: str, group_id: str) -> Optional[KGParagraphHash]:
        """
        保存段落 hash

        Args:
            hash_value: Hash 值
            group_id: 群组 ID

        Returns:
            Optional[KGParagraphHash]: 记录对象
        """
        try:
            return await self.create(
                hash_value=hash_value,
                group_id=group_id,
                created_time=time.time(),
            )
        except Exception as e:
            # 唯一约束冲突表示已存在
            await self.session.rollback()
            logger.debug(f"[KnowledgeParagraphHashRepository] 保存 hash 失败（可能已存在）: {e}")
            return None

    async def exists_hash(self, hash_value: str, group_id: str) -> bool:
        """
        检查段落 hash 是否已存在

        Args:
            hash_value: Hash 值
            group_id: 群组 ID

        Returns:
            bool: 是否存在
        """
        try:
            stmt = select(func.count()).select_from(KGParagraphHash).where(and_(
                KGParagraphHash.hash_value == hash_value,
                KGParagraphHash.group_id == group_id,
            ))
            result = await self.session.execute(stmt)
            return (result.scalar() or 0) > 0
        except Exception as e:
            logger.error(f"[KnowledgeParagraphHashRepository] 检查 hash 失败: {e}")
            return False
