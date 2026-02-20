"""
人格学习和风格学习相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, DateTime, Boolean
from sqlalchemy.sql import func
from .base import Base


class PersonaLearningReview(Base):
    """人格学习审核表 - 匹配传统数据库 persona_update_reviews 表"""
    __tablename__ = 'persona_update_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Float, nullable=False) # 使用 REAL/Float 以匹配传统数据库
    group_id = Column(String(255), nullable=False, index=True)
    update_type = Column(String(255), nullable=False) # personality_trait, background_story, speaking_style, etc.
    original_content = Column(Text)
    new_content = Column(Text)
    proposed_content = Column(Text) # 建议的新内容（兼容字段）
    confidence_score = Column(Float) # 置信度得分
    reason = Column(Text) # 学习原因
    status = Column(String(50), default='pending', nullable=False) # pending/approved/rejected
    reviewer_comment = Column(Text)
    review_time = Column(Float) # 使用 REAL/Float 以匹配传统数据库
    metadata_ = Column('metadata', Text) # JSON格式的元数据，使用 metadata_ 避免与 SQLAlchemy 保留字冲突

    __table_args__ = (
        Index('idx_group_persona_review', 'group_id', 'status'),
        Index('idx_persona_review_timestamp', 'timestamp'),
        Index('idx_persona_review_status', 'status'),
    )


class StyleLearningReview(Base):
    """风格学习审核表 - 匹配传统数据库 style_learning_reviews 表"""
    __tablename__ = 'style_learning_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), nullable=False) # 学习类型
    group_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(Float, nullable=False) # 使用 REAL/Float 以匹配传统数据库
    learned_patterns = Column(Text) # JSON格式存储学习的模式
    few_shots_content = Column(Text) # Few-shot 示例内容
    status = Column(String(50), default='pending') # pending/approved/rejected
    description = Column(Text) # 描述信息
    reviewer_comment = Column(Text) # 审查评论
    review_time = Column(Float) # 审查时间
    # 修改为 DateTime 类型以兼容 MySQL 的 DATETIME
    # SQLite 使用 TIMESTAMP，MySQL 使用 DATETIME，SQLAlchemy 的 DateTime 可以自动适配
    created_at = Column(DateTime) # 创建时间
    updated_at = Column(DateTime) # 更新时间

    __table_args__ = (
        Index('idx_status', 'status'),
        Index('idx_group', 'group_id'),
        Index('idx_timestamp', 'timestamp'),
    )


class StyleLearningPattern(Base):
    """风格学习模式表（已批准的模式）"""
    __tablename__ = 'style_learning_patterns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), nullable=False, index=True)
    pattern_type = Column(String(50), nullable=False)
    pattern = Column(Text, nullable=False)
    usage_count = Column(Integer, default=0) # 使用次数
    confidence = Column(Float, default=1.0) # 置信度
    last_used = Column(BigInteger) # 最后使用时间
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_group_pattern_type', 'group_id', 'pattern_type'),
        Index('idx_pattern_usage', 'usage_count'),
        Index('idx_pattern_last_used', 'last_used'),
    )


class InteractionRecord(Base):
    """互动记录表（用于趋势分析）"""
    __tablename__ = 'interaction_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    interaction_type = Column(String(50), nullable=False) # message, reaction, mention, etc.
    content_preview = Column(String(200))
    timestamp = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_group_user_interaction', 'group_id', 'user_id'),
        Index('idx_interaction_timestamp', 'timestamp'),
        Index('idx_interaction_type', 'interaction_type'),
    )


class LearningBatch(Base):
    """学习批次表 - 匹配 learning_batches 表"""
    __tablename__ = 'learning_batches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(255), unique=True, nullable=True, index=True)
    batch_name = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    processed_messages = Column(Integer, default=0)
    message_count = Column(Integer, default=0)
    filtered_count = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    status = Column(String(50), default='pending')
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_group', 'group_id'),
        Index('idx_batch_id', 'batch_id'),
        Index('idx_batch_name', 'batch_name'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'batch_name': self.batch_name,
            'group_id': self.group_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'quality_score': self.quality_score,
            'processed_messages': self.processed_messages,
            'message_count': self.message_count,
            'filtered_count': self.filtered_count,
            'success': self.success,
            'error_message': self.error_message,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class LearningSession(Base):
    """学习会话表 - 匹配 learning_sessions 表"""
    __tablename__ = 'learning_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    batch_id = Column(String(255), nullable=True) # 外键到 learning_batches.batch_id
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=True)
    message_count = Column(Integer, default=0)
    learning_quality = Column(Float, nullable=True)
    status = Column(String(50), default='active')
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_group', 'group_id'),
        Index('idx_session_id', 'session_id'),
        Index('idx_batch_id', 'batch_id'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'group_id': self.group_id,
            'batch_id': self.batch_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'message_count': self.message_count,
            'learning_quality': self.learning_quality,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class LearningReinforcementFeedback(Base):
    """学习强化反馈表 - 记录学习过程的反馈和优化信息"""
    __tablename__ = 'learning_reinforcement_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    feedback_type = Column(String(100), nullable=False) # positive, negative, neutral
    feedback_content = Column(Text, nullable=True) # 详细反馈内容
    effectiveness_score = Column(Float, nullable=True) # 反馈有效性评分
    applied_at = Column(Float, nullable=False) # 应用时间戳
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_group', 'group_id'),
        Index('idx_feedback_type', 'feedback_type'),
        Index('idx_applied_at', 'applied_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'feedback_type': self.feedback_type,
            'feedback_content': self.feedback_content,
            'effectiveness_score': self.effectiveness_score,
            'applied_at': self.applied_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class LearningOptimizationLog(Base):
    """学习优化日志表 - 记录学习参数优化的历史"""
    __tablename__ = 'learning_optimization_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    optimization_type = Column(String(100), nullable=False) # parameter_tuning, strategy_adjustment, etc.
    parameters = Column(Text, nullable=True) # JSON格式的参数配置
    before_metrics = Column(Text, nullable=True) # JSON格式的优化前指标
    after_metrics = Column(Text, nullable=True) # JSON格式的优化后指标
    improvement_rate = Column(Float, nullable=True) # 改进率
    applied_at = Column(Float, nullable=False) # 应用时间戳
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_group', 'group_id'),
        Index('idx_optimization_type', 'optimization_type'),
        Index('idx_applied_at', 'applied_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'optimization_type': self.optimization_type,
            'parameters': self.parameters,
            'before_metrics': self.before_metrics,
            'after_metrics': self.after_metrics,
            'improvement_rate': self.improvement_rate,
            'applied_at': self.applied_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

