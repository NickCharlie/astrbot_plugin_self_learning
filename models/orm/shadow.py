"""Persistent shadow-mode profiles."""

from sqlalchemy import BigInteger, Boolean, Column, Index, Integer, String, Text

from .base import Base


class ShadowProfile(Base):
    """A learned language-behaviour profile for one chat participant."""

    __tablename__ = "shadow_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_group_id = Column(String(255), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)
    source_group_id = Column(String(255), nullable=False, index=True)
    sender_id = Column(String(255), nullable=False, index=True)
    sender_name = Column(String(255), nullable=False)
    sender_qq = Column(String(32), nullable=True)
    profile_data = Column(Text, nullable=False)
    sample_count = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("idx_shadow_target_enabled", "target_group_id", "enabled"),
        Index(
            "idx_shadow_source_sender",
            "source_type",
            "source_group_id",
            "sender_id",
        ),
    )
