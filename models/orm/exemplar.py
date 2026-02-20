"""
Exemplar ORM model.

Stores high-quality message examples used for few-shot style imitation.
Each exemplar captures the original text along with its embedding vector
for similarity-based retrieval.
"""

import time

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from .base import Base


class Exemplar(Base):
    """Few-shot style exemplar record.

    Attributes:
        id: Auto-increment primary key.
        content: The original message text serving as style example.
        sender_id: ID of the message sender.
        group_id: Chat group identifier.
        embedding_json: Serialised embedding vector (JSON float array).
        weight: Quality weight (adjusted by feedback, default 1.0).
        dimensions: Embedding vector dimensionality (for validation).
        created_at: Unix timestamp of record creation.
        updated_at: Unix timestamp of last update.
    """

    __tablename__ = "exemplar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    sender_id = Column(String(255), nullable=True)
    group_id = Column(String(255), nullable=False)
    embedding_json = Column(Text, nullable=True)
    weight = Column(Float, default=1.0)
    dimensions = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_exemplar_group_id", "group_id"),
        Index("idx_exemplar_weight", "weight"),
        Index("idx_exemplar_group_weight", "group_id", "weight"),
    )
