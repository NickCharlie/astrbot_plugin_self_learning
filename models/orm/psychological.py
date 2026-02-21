"""
心理状态系统相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class CompositePsychologicalState(Base):
    """复合心理状态表"""
    __tablename__ = 'composite_psychological_states'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, default='', server_default='')
    state_id = Column(String(255), nullable=False, unique=True)
    overall_state = Column(String(100), nullable=False, default='neutral', server_default='neutral')
    state_intensity = Column(Float, nullable=False, default=0.5)
    last_transition_time = Column(BigInteger, nullable=True)
    triggering_events = Column(Text) # JSON 格式
    context = Column(Text) # JSON 格式
    created_at = Column(BigInteger, nullable=False)
    last_updated = Column(BigInteger, nullable=False)

    # 关系
    components = relationship("PsychologicalStateComponent", back_populates="composite_state", lazy="selectin")

    __table_args__ = (
        Index('idx_psych_state_group', 'group_id'),
        Index('idx_psych_state_group_user', 'group_id', 'user_id', unique=True),
    )


class PsychologicalStateComponent(Base):
    """心理状态组件表"""
    __tablename__ = 'psychological_state_components'

    id = Column(Integer, primary_key=True, autoincrement=True)
    composite_state_id = Column(Integer, ForeignKey('composite_psychological_states.id'), nullable=True) # 允许 NULL 兼容传统数据
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


class PersonaDiversityScore(Base):
    """人格多样性评分表 - 记录人格在不同维度的多样性"""
    __tablename__ = 'persona_diversity_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    persona_id = Column(String(255), nullable=False, index=True)
    diversity_dimension = Column(String(100), nullable=False) # emotion, topic, style, etc.
    score = Column(Float, nullable=False) # 多样性分数 0-1
    calculated_at = Column(Float, nullable=False) # 计算时间戳
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_diversity_group', 'group_id'),
        Index('idx_diversity_persona', 'persona_id'),
        Index('idx_diversity_dimension', 'diversity_dimension'),
        Index('idx_diversity_calculated', 'calculated_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'persona_id': self.persona_id,
            'diversity_dimension': self.diversity_dimension,
            'score': self.score,
            'calculated_at': self.calculated_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PersonaAttributeWeight(Base):
    """人格属性权重表 - 记录人格各属性的权重配置"""
    __tablename__ = 'persona_attribute_weights'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    persona_id = Column(String(255), nullable=False, index=True)
    attribute_name = Column(String(100), nullable=False) # 属性名称
    weight = Column(Float, nullable=False) # 权重值 0-1
    adjustment_reason = Column(Text, nullable=True) # 调整原因
    updated_at = Column(Float, nullable=False) # 更新时间戳
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_weight_group', 'group_id'),
        Index('idx_weight_persona', 'persona_id'),
        Index('idx_weight_attribute', 'attribute_name'),
        Index('idx_weight_updated', 'updated_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'persona_id': self.persona_id,
            'attribute_name': self.attribute_name,
            'weight': self.weight,
            'adjustment_reason': self.adjustment_reason,
            'updated_at': self.updated_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PersonaEvolutionSnapshot(Base):
    """人格演化快照表 - 记录人格在不同时间点的完整状态"""
    __tablename__ = 'persona_evolution_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    persona_id = Column(String(255), nullable=False, index=True)
    snapshot_data = Column(Text, nullable=False) # JSON格式的完整人格状态
    version = Column(Integer, nullable=False) # 版本号
    snapshot_timestamp = Column(Float, nullable=False) # 快照时间戳
    trigger_event = Column(Text, nullable=True) # 触发事件描述
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_snapshot_group', 'group_id'),
        Index('idx_snapshot_persona', 'persona_id'),
        Index('idx_snapshot_version', 'version'),
        Index('idx_snapshot_timestamp', 'snapshot_timestamp'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'persona_id': self.persona_id,
            'snapshot_data': self.snapshot_data,
            'version': self.version,
            'snapshot_timestamp': self.snapshot_timestamp,
            'trigger_event': self.trigger_event,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EmotionProfile(Base):
    """Emotion profile per user per group."""
    __tablename__ = 'emotion_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    dominant_emotions = Column(Text) # JSON
    emotion_patterns = Column(Text) # JSON
    empathy_level = Column(Float, default=0.5)
    emotional_stability = Column(Float, default=0.5)
    last_updated = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_emotion_user_group', 'user_id', 'group_id', unique=True),
    )


class BotMood(Base):
    """Bot mood state per group."""
    __tablename__ = 'bot_mood'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    mood_type = Column(String(100), nullable=False)
    mood_intensity = Column(Float, default=0.5)
    mood_description = Column(Text)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float)
    is_active = Column(Integer, default=1) # Boolean as int for SQLite compat
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_mood_group_active', 'group_id', 'is_active'),
    )


class PersonaBackup(Base):
    """Persona configuration backup."""
    __tablename__ = 'persona_backups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, default='default', server_default='default', index=True)
    backup_name = Column(String(255), nullable=False)
    timestamp = Column(Float, nullable=False)
    reason = Column(Text)
    persona_config = Column(Text) # JSON
    original_persona = Column(Text) # JSON
    imitation_dialogues = Column(Text) # JSON
    backup_reason = Column(Text)
    backup_time = Column(Float, nullable=True)  # legacy column in production DB
    persona_content = Column(Text, nullable=True, default='', server_default='')  # legacy column in production DB
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_backup_timestamp', 'timestamp'),
    )
