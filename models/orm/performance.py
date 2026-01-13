"""
学习性能记录相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, Index, BigInteger
from .base import Base


class LearningPerformanceHistory(Base):
    """学习性能历史记录表"""
    __tablename__ = 'learning_performance_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255))
    timestamp = Column(BigInteger, nullable=False)
    quality_score = Column(Float)
    learning_time = Column(Float)
    success = Column(Boolean)
    successful_pattern = Column(Text)
    failed_pattern = Column(Text)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_performance_group', 'group_id'),
        Index('idx_performance_session', 'session_id'),
        Index('idx_performance_timestamp', 'timestamp'),
    )
