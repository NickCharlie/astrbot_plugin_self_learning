"""
心理状态系统相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class CompositePsychologicalState(Base):
    """复合心理状态表"""
    __tablename__ = 'composite_psychological_states'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True, unique=True)
    state_id = Column(String(255), nullable=False, unique=True)
    triggering_events = Column(Text)  # JSON 格式
    context = Column(Text)  # JSON 格式
    created_at = Column(BigInteger, nullable=False)
    last_updated = Column(BigInteger, nullable=False)

    # 关系
    components = relationship("PsychologicalStateComponent", back_populates="composite_state", lazy="selectin")

    __table_args__ = (
        Index('idx_psych_state_group', 'group_id'),
    )


class PsychologicalStateComponent(Base):
    """心理状态组件表"""
    __tablename__ = 'psychological_state_components'

    id = Column(Integer, primary_key=True, autoincrement=True)
    composite_state_id = Column(Integer, ForeignKey('composite_psychological_states.id'), nullable=False)
    group_id = Column(String(255), nullable=False, index=True)
    state_id = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    state_type = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    threshold = Column(Float, default=0.3, nullable=False)
    description = Column(Text)
    start_time = Column(BigInteger, nullable=False)

    # 关系
    composite_state = relationship("CompositePsychologicalState", back_populates="components")

    __table_args__ = (
        Index('idx_psych_component_composite', 'composite_state_id'),
        Index('idx_psych_component_state', 'state_id'),
        Index('idx_psych_component_category', 'category'),
    )


class PsychologicalStateHistory(Base):
    """心理状态变化历史表"""
    __tablename__ = 'psychological_state_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    state_id = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    old_state_type = Column(String(100))
    new_state_type = Column(String(100), nullable=False)
    old_value = Column(Float)
    new_value = Column(Float, nullable=False)
    change_reason = Column(Text)
    timestamp = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_psych_history_group', 'group_id'),
        Index('idx_psych_history_timestamp', 'timestamp'),
    )
