"""
黑话相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Index, DateTime, BigInteger
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

    __table_args__ = (
        Index('idx_jargon_content', 'content', mysql_length=255),
        Index('idx_jargon_chat_id', 'chat_id'),
        Index('idx_jargon_is_jargon', 'is_jargon'),
        Index('uk_chat_content', 'chat_id', 'content', unique=True, mysql_length={'content': 255}),  # 唯一索引，MySQL 限制 TEXT 前255字符
    )
