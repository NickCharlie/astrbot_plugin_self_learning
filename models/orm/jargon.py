"""
黑话相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Index, DateTime, BigInteger, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base


class Jargon(Base):
    """黑话表 - 匹配传统数据库 jargon 表"""
    __tablename__ = 'jargon'

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    raw_content = Column(Text)  # JSON 格式存储原始内容
    meaning = Column(Text)
    is_jargon = Column(Boolean)
    count = Column(Integer, default=1)
    last_inference_count = Column(Integer, default=0)
    is_complete = Column(Boolean, default=False)
    is_global = Column(Boolean, default=False)
    chat_id = Column(String(255), nullable=False, index=True)
    # 使用 BigInteger 存储 Unix 时间戳（自动迁移会将 DATETIME 转换为 BIGINT）
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    # 关系
    usage_frequencies = relationship("JargonUsageFrequency", back_populates="jargon", lazy="selectin")

    __table_args__ = (
        Index('idx_jargon_content', 'content', mysql_length=255),
        Index('idx_jargon_chat_id', 'chat_id'),
        Index('idx_jargon_is_jargon', 'is_jargon'),
        Index('uk_chat_content', 'chat_id', 'content', unique=True, mysql_length={'content': 255}),  # 唯一索引，MySQL 限制 TEXT 前255字符
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'raw_content': self.raw_content,
            'meaning': self.meaning,
            'is_jargon': self.is_jargon,
            'count': self.count,
            'last_inference_count': self.last_inference_count,
            'is_complete': self.is_complete,
            'is_global': self.is_global,
            'chat_id': self.chat_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class JargonUsageFrequency(Base):
    """黑话使用频率表 - 记录黑话的使用统计"""
    __tablename__ = 'jargon_usage_frequency'

    id = Column(Integer, primary_key=True, autoincrement=True)
    jargon_id = Column(Integer, ForeignKey('jargon.id'), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(Float, nullable=False)  # Unix timestamp
    success_rate = Column(Float, nullable=True)  # 理解成功率 0-1
    context_types = Column(Text, nullable=True)  # JSON - 使用场景类型列表
    created_at = Column(DateTime, default=func.now())

    # 关系
    jargon = relationship("Jargon", back_populates="usage_frequencies")

    __table_args__ = (
        Index('idx_usage_jargon', 'jargon_id'),
        Index('idx_usage_group', 'group_id'),
        Index('idx_usage_last_used', 'last_used_at'),
        Index('idx_usage_count', 'usage_count'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'jargon_id': self.jargon_id,
            'group_id': self.group_id,
            'usage_count': self.usage_count,
            'last_used_at': self.last_used_at,
            'success_rate': self.success_rate,
            'context_types': self.context_types,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

