"""
表达模式学习相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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

    # 关系
    generation_results = relationship("ExpressionGenerationResult", back_populates="pattern", lazy="selectin")

    __table_args__ = (
        Index('idx_group_weight', 'group_id', 'weight'),
        Index('idx_group_active', 'group_id', 'last_active_time'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'situation': self.situation,
            'expression': self.expression,
            'weight': self.weight,
            'last_active_time': self.last_active_time,
            'create_time': self.create_time
        }


class ExpressionGenerationResult(Base):
    """表达生成结果表 - 记录基于模式生成的表达结果及反馈"""
    __tablename__ = 'expression_generation_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    pattern_id = Column(Integer, ForeignKey('expression_patterns.id'), nullable=False, index=True)
    generated_text = Column(Text, nullable=False)  # 生成的文本
    context = Column(Text, nullable=True)  # JSON - 生成时的上下文
    quality_score = Column(Float, nullable=True)  # 质量评分 0-1
    user_feedback = Column(String(50), nullable=True)  # 用户反馈：positive/negative/neutral
    generated_at = Column(Float, nullable=False)  # Unix timestamp
    created_at = Column(DateTime, default=func.now())

    # 关系
    pattern = relationship("ExpressionPattern", back_populates="generation_results")

    __table_args__ = (
        Index('idx_gen_group', 'group_id'),
        Index('idx_gen_pattern', 'pattern_id'),
        Index('idx_gen_generated', 'generated_at'),
        Index('idx_gen_feedback', 'user_feedback'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'pattern_id': self.pattern_id,
            'generated_text': self.generated_text,
            'context': self.context,
            'quality_score': self.quality_score,
            'user_feedback': self.user_feedback,
            'generated_at': self.generated_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AdaptiveResponseTemplate(Base):
    """自适应响应模板表 - 存储可动态调整的响应模板"""
    __tablename__ = 'adaptive_response_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    template_text = Column(Text, nullable=False)  # 模板文本，包含占位符如 {name}, {emotion}
    trigger_patterns = Column(Text, nullable=False)  # JSON - 触发条件模式列表
    usage_count = Column(Integer, default=0)
    success_rate = Column(Float, nullable=True)  # 成功率 0-1
    last_adapted_at = Column(Float, nullable=False)  # 最后调整时间
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_template_group', 'group_id'),
        Index('idx_template_usage', 'usage_count'),
        Index('idx_template_adapted', 'last_adapted_at'),
        Index('idx_template_success', 'success_rate'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'template_text': self.template_text,
            'trigger_patterns': self.trigger_patterns,
            'usage_count': self.usage_count,
            'success_rate': self.success_rate,
            'last_adapted_at': self.last_adapted_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class StyleProfile(Base):
    """Aggregate style profile for a persona or learning context."""
    __tablename__ = 'style_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_name = Column(String(255), nullable=False)
    vocabulary_richness = Column(Float)
    sentence_complexity = Column(Float)
    emotional_expression = Column(Float)
    interaction_tendency = Column(Float)
    topic_diversity = Column(Float)
    formality_level = Column(Float)
    creativity_score = Column(Float)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_style_profile_name', 'profile_name'),
    )


class StyleLearningRecord(Base):
    """Record of a style learning session."""
    __tablename__ = 'style_learning_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    style_type = Column(String(100), nullable=False)
    learned_patterns = Column(Text)  # JSON
    confidence_score = Column(Float)
    sample_count = Column(Integer)
    last_updated = Column(Float)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_style_record_type', 'style_type'),
    )


class LanguageStylePattern(Base):
    """Reusable language style pattern with example phrases."""
    __tablename__ = 'language_style_patterns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    language_style = Column(String(255), nullable=False)
    example_phrases = Column(Text)  # JSON
    usage_frequency = Column(Integer, default=0)
    context_type = Column(String(100), default='general')
    confidence_score = Column(Float)
    last_updated = Column(Float)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_lang_style', 'language_style'),
        Index('idx_lang_context', 'context_type'),
    )

