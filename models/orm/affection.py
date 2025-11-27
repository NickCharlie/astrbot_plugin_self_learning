"""
好感度系统相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, Index, BigInteger
from sqlalchemy.orm import relationship
from .base import Base


class UserAffection(Base):
    """用户好感度表"""
    __tablename__ = 'user_affections'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    affection_level = Column(Integer, default=0, nullable=False)
    max_affection = Column(Integer, default=100, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    # 关系
    interactions = relationship("AffectionInteraction", back_populates="user_affection", lazy="selectin")

    __table_args__ = (
        Index('idx_group_user_affection', 'group_id', 'user_id', unique=True),
    )


class AffectionInteraction(Base):
    """好感度交互记录表"""
    __tablename__ = 'affection_interactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_affection_id = Column(Integer, ForeignKey('user_affections.id'), nullable=False)
    interaction_type = Column(String(50), nullable=False)
    affection_delta = Column(Integer, nullable=False)
    message_content = Column(Text)
    timestamp = Column(BigInteger, nullable=False)

    # 关系
    user_affection = relationship("UserAffection", back_populates="interactions")

    __table_args__ = (
        Index('idx_user_affection_interaction', 'user_affection_id'),
        Index('idx_interaction_timestamp', 'timestamp'),
    )


class UserConversationHistory(Base):
    """用户对话历史表"""
    __tablename__ = 'user_conversation_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    turn_index = Column(Integer, nullable=False)

    __table_args__ = (
        Index('idx_group_user_history', 'group_id', 'user_id'),
        Index('idx_history_timestamp', 'timestamp'),
    )


class UserDiversity(Base):
    """用户多样性记录表"""
    __tablename__ = 'user_diversity'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    response_hash = Column(String(64), nullable=False)
    response_preview = Column(String(200))
    timestamp = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_group_user_diversity', 'group_id', 'user_id'),
        Index('idx_diversity_timestamp', 'timestamp'),
    )
