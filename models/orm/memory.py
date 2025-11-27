"""
记忆系统相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger
from .base import Base


class Memory(Base):
    """记忆表"""
    __tablename__ = 'memories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=5, nullable=False)
    memory_type = Column(String(50), default='conversation')
    created_at = Column(BigInteger, nullable=False)
    last_accessed = Column(BigInteger, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index('idx_group_user_memory', 'group_id', 'user_id'),
        Index('idx_memory_importance', 'importance'),
        Index('idx_memory_accessed', 'last_accessed'),
    )


class MemoryEmbedding(Base):
    """记忆向量表"""
    __tablename__ = 'memory_embeddings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(Integer, nullable=False, index=True)
    embedding_model = Column(String(100), nullable=False)
    embedding_data = Column(Text, nullable=False)  # JSON 格式存储向量
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_memory_embedding', 'memory_id', 'embedding_model', unique=True),
    )


class MemorySummary(Base):
    """记忆摘要表"""
    __tablename__ = 'memory_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    summary_type = Column(String(50), nullable=False)
    summary_content = Column(Text, nullable=False)
    memory_count = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_group_user_summary', 'group_id', 'user_id', 'summary_type'),
    )
