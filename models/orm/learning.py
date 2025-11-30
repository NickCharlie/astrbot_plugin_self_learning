"""
人格学习和风格学习相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, DateTime
from .base import Base


class PersonaLearningReview(Base):
    """人格学习审核表 - 匹配传统数据库 persona_update_reviews 表"""
    __tablename__ = 'persona_update_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Float, nullable=False)  # 使用 REAL/Float 以匹配传统数据库
    group_id = Column(String(255), nullable=False, index=True)
    update_type = Column(String(255), nullable=False)  # personality_trait, background_story, speaking_style, etc.
    original_content = Column(Text)
    new_content = Column(Text)
    proposed_content = Column(Text)  # 建议的新内容（兼容字段）
    confidence_score = Column(Float)  # 置信度得分
    reason = Column(Text)  # 学习原因
    status = Column(String(50), default='pending', nullable=False)  # pending/approved/rejected
    reviewer_comment = Column(Text)
    review_time = Column(Float)  # 使用 REAL/Float 以匹配传统数据库
    metadata_ = Column('metadata', Text)  # JSON格式的元数据，使用 metadata_ 避免与 SQLAlchemy 保留字冲突

    __table_args__ = (
        Index('idx_group_persona_review', 'group_id', 'status'),
        Index('idx_persona_review_timestamp', 'timestamp'),
        Index('idx_persona_review_status', 'status'),
    )


class StyleLearningReview(Base):
    """风格学习审核表 - 匹配传统数据库 style_learning_reviews 表"""
    __tablename__ = 'style_learning_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), nullable=False)  # 学习类型
    group_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(Float, nullable=False)  # 使用 REAL/Float 以匹配传统数据库
    learned_patterns = Column(Text)  # JSON格式存储学习的模式
    few_shots_content = Column(Text)  # Few-shot 示例内容
    status = Column(String(50), default='pending')  # pending/approved/rejected
    description = Column(Text)  # 描述信息
    reviewer_comment = Column(Text)  # 审查评论
    review_time = Column(Float)  # 审查时间
    # ✅ 修改为 DateTime 类型以兼容 MySQL 的 DATETIME
    # SQLite 使用 TIMESTAMP，MySQL 使用 DATETIME，SQLAlchemy 的 DateTime 可以自动适配
    created_at = Column(DateTime)  # 创建时间
    updated_at = Column(DateTime)  # 更新时间

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
    usage_count = Column(Integer, default=0)  # 使用次数
    confidence = Column(Float, default=1.0)  # 置信度
    last_used = Column(BigInteger)  # 最后使用时间
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
    interaction_type = Column(String(50), nullable=False)  # message, reaction, mention, etc.
    content_preview = Column(String(200))
    timestamp = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_group_user_interaction', 'group_id', 'user_id'),
        Index('idx_interaction_timestamp', 'timestamp'),
        Index('idx_interaction_type', 'interaction_type'),
    )
