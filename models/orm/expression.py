"""
表达模式学习相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index
from .base import Base


class ExpressionPattern(Base):
    """表达模式表 - 存储学习到的表达习惯"""
    __tablename__ = 'expression_patterns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    situation = Column(Text, nullable=False)  # 场景描述
    expression = Column(Text, nullable=False)  # 表达方式
    weight = Column(Float, default=1.0, nullable=False)  # 权重
    last_active_time = Column(Float, nullable=False)  # 最后活跃时间
    create_time = Column(Float, nullable=False)  # 创建时间

    __table_args__ = (
        Index('idx_group_weight', 'group_id', 'weight'),
        Index('idx_group_active', 'group_id', 'last_active_time'),
    )
