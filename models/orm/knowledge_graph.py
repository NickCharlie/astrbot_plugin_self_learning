"""
知识图谱相关的 ORM 模型

注意：字段长度受 MySQL utf8mb4 索引限制（最大 3072 字节），
组合唯一约束中的总字符数 * 4 不得超过 3072。
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, UniqueConstraint
from .base import Base


class KGEntity(Base):
    """知识图谱实体表"""
    __tablename__ = 'kg_entities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    entity_type = Column(String(100), default='general')
    appear_count = Column(Integer, default=1)
    last_active_time = Column(Float, nullable=False)
    group_id = Column(String(100), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('name', 'group_id', name='uq_kg_entity_name_group'),
        Index('idx_kg_entity_group', 'group_id'),
        Index('idx_kg_entity_count', 'appear_count'),
    )


class KGRelation(Base):
    """知识图谱关系表"""
    __tablename__ = 'kg_relations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(255), nullable=False, index=True)
    predicate = Column(String(255), nullable=False)
    object = Column(String(255), nullable=False, index=True)
    confidence = Column(Float, default=1.0)
    created_time = Column(Float, nullable=False)
    group_id = Column(String(100), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('subject', 'predicate', 'object', 'group_id', name='uq_kg_relation'),
        Index('idx_kg_relation_group', 'group_id'),
        Index('idx_kg_relation_subject', 'subject', 'group_id'),
        Index('idx_kg_relation_object', 'object', 'group_id'),
    )


class KGParagraphHash(Base):
    """知识图谱段落hash表（用于去重）"""
    __tablename__ = 'kg_paragraph_hashes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    hash_value = Column(String(64), nullable=False, index=True)
    group_id = Column(String(100), nullable=False, index=True)
    created_time = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint('hash_value', 'group_id', name='uq_kg_paragraph_hash'),
    )
