"""
消息相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, Index, BigInteger
from .base import Base


class RawMessage(Base):
    """原始消息表"""
    __tablename__ = 'raw_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String(255), nullable=False, index=True)
    sender_name = Column(String(255))
    message = Column(Text, nullable=False)
    group_id = Column(String(255), index=True)
    timestamp = Column(BigInteger, nullable=False)
    platform = Column(String(100))
    message_id = Column(String(255), nullable=True)  # 可能在旧表中不存在
    reply_to = Column(String(255), nullable=True)    # 可能在旧表中不存在
    created_at = Column(BigInteger, nullable=False)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_raw_timestamp', 'timestamp'),
        Index('idx_raw_sender', 'sender_id'),
        Index('idx_raw_processed', 'processed'),
        Index('idx_raw_group', 'group_id'),
    )


class FilteredMessage(Base):
    """筛选后消息表"""
    __tablename__ = 'filtered_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_message_id = Column(Integer)
    message = Column(Text, nullable=False)
    sender_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), index=True)
    timestamp = Column(BigInteger, nullable=False)
    confidence = Column(Float)
    quality_scores = Column(Text)  # JSON 字符串，存储多个质量分数（与传统 database_manager 保持一致）
    filter_reason = Column(Text)
    created_at = Column(BigInteger, nullable=False)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_filtered_timestamp', 'timestamp'),
        Index('idx_filtered_sender', 'sender_id'),
        Index('idx_filtered_processed', 'processed'),
        Index('idx_filtered_group', 'group_id'),
    )


class BotMessage(Base):
    """Bot消息表"""
    __tablename__ = 'bot_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_bot_timestamp', 'timestamp'),
        Index('idx_bot_group', 'group_id'),
    )
