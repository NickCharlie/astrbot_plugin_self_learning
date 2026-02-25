"""
Exemplar ORM model.

Stores high-quality message examples used for few-shot style imitation.
Each exemplar captures the original text along with its embedding vector
for similarity-based retrieval.

Effectiveness tracking (inspired by ACE helpful/harmful counters):
    helpful_count and harmful_count track user feedback signals to
    distinguish high-quality exemplars from ineffective ones. The dual
    counter design uses Laplace smoothing to avoid cold-start bias.
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
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from .base import Base

# MEDIUMTEXT on MySQL (16 MB), plain TEXT on SQLite (no size limit).
# Required for high-dimensional embedding vectors (e.g. 3072-dim ≈ 69 KB JSON).
_EmbeddingText = Text().with_variant(MEDIUMTEXT(), "mysql")


class Exemplar(Base):
    """Few-shot style exemplar record.

    Attributes:
        id: Auto-increment primary key.
        content: The original message text serving as style example.
        sender_id: ID of the message sender.
        group_id: Chat group identifier.
        embedding_json: Serialised embedding vector (JSON float array).
        weight: Quality weight (adjusted by feedback, default 1.0).
        helpful_count: Number of positive feedback signals received.
        harmful_count: Number of negative feedback signals received.
        dimensions: Embedding vector dimensionality (for validation).
        created_at: Unix timestamp of record creation.
        updated_at: Unix timestamp of last update.
    """

    __tablename__ = "exemplar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    sender_id = Column(String(255), nullable=True)
    group_id = Column(String(255), nullable=False)
    embedding_json = Column(_EmbeddingText, nullable=True)
    weight = Column(Float, default=1.0)
    helpful_count = Column(Integer, default=0, nullable=False, server_default="0")
    harmful_count = Column(Integer, default=0, nullable=False, server_default="0")
    dimensions = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index("idx_exemplar_group_id", "group_id"),
        Index("idx_exemplar_weight", "weight"),
        Index("idx_exemplar_group_weight", "group_id", "weight"),
    )

    @property
    def effectiveness_ratio(self) -> float:
        """Compute effectiveness ratio with Laplace smoothing.

        Returns a value in (0, 1) where 0.5 indicates neutral (no feedback).
        Formula: (helpful + 1) / (helpful + harmful + 2)
        """
        helpful = self.helpful_count or 0
        harmful = self.harmful_count or 0
        return (helpful + 1) / (helpful + harmful + 2)

    @property
    def effective_weight(self) -> float:
        """Compute quality-adjusted weight blending frequency and feedback.

        Combines the base weight (recency/frequency) with the effectiveness
        ratio derived from user feedback signals.
        """
        return (self.weight or 1.0) * self.effectiveness_ratio
