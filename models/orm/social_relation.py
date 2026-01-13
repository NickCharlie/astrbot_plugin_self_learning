"""
社交关系系统相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class SocialRelation(Base):
    """社交关系表 - 匹配传统数据库 social_relations 表（兼容版本）"""
    __tablename__ = 'social_relations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # MySQL 版本字段
    user_id = Column(String(255))  # MySQL 使用 user_id
    # SQLite 版本字段（兼容）
    from_user = Column(String(255))  # SQLite 使用 from_user
    to_user = Column(String(255))    # SQLite 使用 to_user

    group_id = Column(String(255), index=True)
    relation_type = Column(String(100))

    # MySQL 版本字段
    affection_score = Column(Float, default=0)
    interaction_count = Column(Integer, default=0)

    # SQLite 版本字段（兼容）
    strength = Column(Float)      # SQLite 使用 strength
    frequency = Column(Integer)   # SQLite 使用 frequency

    last_interaction = Column(Float)
    metadata_ = Column('metadata', Text)  # JSON 格式（MySQL 版本），使用 metadata_ 避免与 SQLAlchemy 保留字冲突

    # 使用 BigInteger 存储 Unix 时间戳（自动迁移会将 DATETIME 转换为 BIGINT）
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)

    __table_args__ = (
        Index('idx_group', 'group_id'),
        Index('idx_affection', 'affection_score'),
        # MySQL 的唯一索引
        Index('uk_user_group', 'user_id', 'group_id', unique=True),
        # SQLite 的唯一索引
        Index('uk_from_to_type', 'from_user', 'to_user', 'relation_type', unique=True),
    )


class UserSocialProfile(Base):
    """用户社交档案表"""
    __tablename__ = 'user_social_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    total_relations = Column(Integer, default=0, nullable=False)
    significant_relations = Column(Integer, default=0, nullable=False)
    dominant_relation_type = Column(String(100))
    created_at = Column(BigInteger, nullable=False)
    last_updated = Column(BigInteger, nullable=False)

    # 关系
    relation_components = relationship("UserSocialRelationComponent", back_populates="profile", lazy="selectin")

    __table_args__ = (
        Index('idx_social_profile_user_group', 'user_id', 'group_id', unique=True),
    )


class UserSocialRelationComponent(Base):
    """用户社交关系组件表"""
    __tablename__ = 'user_social_relation_components'

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey('user_social_profiles.id'), nullable=False)
    from_user_id = Column(String(255), nullable=False, index=True)
    to_user_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    relation_type = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    frequency = Column(Integer, default=0, nullable=False)
    last_interaction = Column(BigInteger, nullable=False)
    description = Column(Text)
    tags = Column(Text)  # JSON 格式
    created_at = Column(BigInteger, nullable=False)

    # 关系
    profile = relationship("UserSocialProfile", back_populates="relation_components")

    __table_args__ = (
        Index('idx_social_relation_profile', 'profile_id'),
        Index('idx_social_relation_from_to', 'from_user_id', 'to_user_id', 'group_id'),
        Index('idx_social_relation_type', 'relation_type'),
    )


class SocialRelationHistory(Base):
    """社交关系变化历史表"""
    __tablename__ = 'social_relation_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_user_id = Column(String(255), nullable=False, index=True)
    to_user_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)
    relation_type = Column(String(100), nullable=False)
    old_value = Column(Float)
    new_value = Column(Float, nullable=False)
    change_reason = Column(Text)
    timestamp = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_social_history_from_to', 'from_user_id', 'to_user_id', 'group_id'),
        Index('idx_social_history_timestamp', 'timestamp'),
    )
