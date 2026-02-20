"""
Few-shot exemplar library.

Stores high-quality message examples and retrieves them via cosine
similarity for few-shot style imitation in LLM prompts.

When an ``IEmbeddingProvider`` is available, exemplars are embedded and
similarity search uses vector cosine distance.  Without an embedding
provider the library degrades to recency-weighted random sampling.

Design notes:
    - Embedding vectors stored as JSON text columns for DB portability.
    - Cosine similarity computed in Python (numpy) during retrieval.
    - Weight field supports feedback-driven quality adjustment.
    - Thread-safe for single-event-loop asyncio usage.
"""

import json
import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger
from sqlalchemy import case, delete, desc, select, update
from sqlalchemy.sql import func

from ..models.orm.exemplar import Exemplar


# Minimum content length to accept as an exemplar.
_MIN_CONTENT_LENGTH = 10

# Maximum exemplars stored per group (FIFO eviction of lowest-weight).
_MAX_EXEMPLARS_PER_GROUP = 500

# Default number of few-shot examples to retrieve.
_DEFAULT_TOP_K = 5


class ExemplarLibrary:
    """Few-shot style exemplar library.

    Usage::

        library = ExemplarLibrary(db_manager, embedding_provider)
        await library.add_exemplar("nice message", group_id, sender_id)
        examples = await library.get_few_shot_examples("query", group_id)
    """

    def __init__(self, db_manager, embedding_provider=None) -> None:
        """Initialise the exemplar library.

        Args:
            db_manager: SQLAlchemy database manager with ``get_session()``.
            embedding_provider: Optional ``IEmbeddingProvider`` for vector
                similarity search.  When ``None``, falls back to
                weight-based random sampling.
        """
        self._db = db_manager
        self._embedding = embedding_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_exemplar(
        self,
        content: str,
        group_id: str,
        sender_id: Optional[str] = None,
    ) -> Optional[int]:
        """Store a high-quality message as a style exemplar.

        Args:
            content: The original message text.
            group_id: Chat group identifier.
            sender_id: Message sender identifier (optional).

        Returns:
            The record ID if saved, or ``None`` if rejected.
        """
        if not content or len(content.strip()) < _MIN_CONTENT_LENGTH:
            return None

        content = content.strip()
        now = int(time.time())

        # Compute embedding if provider is available.
        embedding_json = None
        dimensions = 0
        if self._embedding:
            try:
                vec = await self._embedding.get_embedding(content)
                embedding_json = json.dumps(vec)
                dimensions = len(vec)
            except Exception as exc:
                logger.debug(
                    f"[ExemplarLibrary] Embedding failed for exemplar, "
                    f"storing without vector: {exc}"
                )

        try:
            async with self._db.get_session() as session:
                record = Exemplar(
                    content=content,
                    sender_id=sender_id,
                    group_id=group_id,
                    embedding_json=embedding_json,
                    weight=1.0,
                    dimensions=dimensions,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                await session.flush()
                record_id = record.id
                await session.commit()

                # Evict excess exemplars if over capacity.
                await self._evict_excess(session, group_id)

                return record_id

        except Exception as exc:
            logger.warning(f"[ExemplarLibrary] Failed to save exemplar: {exc}")
            return None

    async def get_few_shot_examples(
        self,
        query: str,
        group_id: str,
        k: int = _DEFAULT_TOP_K,
    ) -> List[str]:
        """Retrieve the top-K most relevant style exemplars.

        When an embedding provider is available, uses cosine similarity
        between the query embedding and stored exemplar vectors.
        Falls back to weight-ordered sampling otherwise.

        Args:
            query: The current query or context string.
            group_id: Chat group to search within.
            k: Number of exemplars to return.

        Returns:
            List of exemplar content strings, most relevant first.
        """
        if self._embedding:
            try:
                return await self._similarity_search(query, group_id, k)
            except Exception as exc:
                logger.debug(
                    f"[ExemplarLibrary] Similarity search failed, "
                    f"falling back to weight-based: {exc}"
                )

        return await self._weight_based_search(group_id, k)

    async def adjust_weight(
        self, exemplar_id: int, delta: float
    ) -> bool:
        """Adjust an exemplar's quality weight.

        Args:
            exemplar_id: Record ID.
            delta: Weight adjustment (positive or negative).

        Returns:
            ``True`` if the update succeeded.
        """
        try:
            async with self._db.get_session() as session:
                stmt = (
                    update(Exemplar)
                    .where(Exemplar.id == exemplar_id)
                    .values(
                        weight=func.max(0.0, Exemplar.weight + delta),
                        updated_at=int(time.time()),
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        except Exception as exc:
            logger.warning(
                f"[ExemplarLibrary] Weight adjustment failed: {exc}"
            )
            return False

    async def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Return summary statistics for a group's exemplar collection."""
        try:
            async with self._db.get_session() as session:
                stmt = select(
                    func.count(Exemplar.id),
                    func.avg(Exemplar.weight),
                    func.sum(
                        case(
                            (Exemplar.embedding_json.isnot(None), 1),
                            else_=0,
                        )
                    ),
                ).where(Exemplar.group_id == group_id)
                result = await session.execute(stmt)
                row = result.one_or_none()

                if row:
                    return {
                        "total_exemplars": row[0] or 0,
                        "avg_weight": round(float(row[1] or 0), 3),
                        "with_embeddings": row[2] or 0,
                    }
        except Exception as exc:
            logger.debug(f"[ExemplarLibrary] Stats query failed: {exc}")

        return {"total_exemplars": 0, "avg_weight": 0.0, "with_embeddings": 0}

    async def delete_exemplar(self, exemplar_id: int) -> bool:
        """Delete a specific exemplar by ID."""
        try:
            async with self._db.get_session() as session:
                stmt = delete(Exemplar).where(Exemplar.id == exemplar_id)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        except Exception as exc:
            logger.warning(f"[ExemplarLibrary] Delete failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _similarity_search(
        self, query: str, group_id: str, k: int
    ) -> List[str]:
        """Vector cosine similarity search."""
        query_vec = await self._embedding.get_embedding(query)

        async with self._db.get_session() as session:
            stmt = (
                select(Exemplar.content, Exemplar.embedding_json, Exemplar.weight)
                .where(
                    Exemplar.group_id == group_id,
                    Exemplar.embedding_json.isnot(None),
                )
                .order_by(desc(Exemplar.weight))
                .limit(_MAX_EXEMPLARS_PER_GROUP)
            )
            result = await session.execute(stmt)
            rows = result.all()

        if not rows:
            return await self._weight_based_search(group_id, k)

        scored = []
        for content, emb_json, weight in rows:
            try:
                stored_vec = json.loads(emb_json)
                sim = self._cosine_similarity(query_vec, stored_vec)
                # Blend similarity with weight for final score.
                score = sim * 0.8 + (weight or 1.0) * 0.2
                scored.append((content, score))
            except (json.JSONDecodeError, TypeError):
                continue

        scored.sort(key=lambda x: x[1], reverse=True)
        return [content for content, _ in scored[:k]]

    async def _weight_based_search(
        self, group_id: str, k: int
    ) -> List[str]:
        """Fallback: return highest-weight exemplars."""
        try:
            async with self._db.get_session() as session:
                stmt = (
                    select(Exemplar.content)
                    .where(Exemplar.group_id == group_id)
                    .order_by(desc(Exemplar.weight), desc(Exemplar.created_at))
                    .limit(k)
                )
                result = await session.execute(stmt)
                return [row[0] for row in result.all()]
        except Exception as exc:
            logger.debug(f"[ExemplarLibrary] Weight search failed: {exc}")
            return []

    async def _evict_excess(self, session, group_id: str) -> None:
        """Remove lowest-weight exemplars when over capacity."""
        try:
            count_stmt = select(func.count(Exemplar.id)).where(
                Exemplar.group_id == group_id
            )
            result = await session.execute(count_stmt)
            total = result.scalar() or 0

            if total <= _MAX_EXEMPLARS_PER_GROUP:
                return

            excess = total - _MAX_EXEMPLARS_PER_GROUP
            # Find IDs of lowest-weight records.
            ids_stmt = (
                select(Exemplar.id)
                .where(Exemplar.group_id == group_id)
                .order_by(Exemplar.weight, Exemplar.created_at)
                .limit(excess)
            )
            result = await session.execute(ids_stmt)
            ids_to_delete = [row[0] for row in result.all()]

            if ids_to_delete:
                del_stmt = delete(Exemplar).where(Exemplar.id.in_(ids_to_delete))
                await session.execute(del_stmt)
                await session.commit()
                logger.debug(
                    f"[ExemplarLibrary] Evicted {len(ids_to_delete)} "
                    f"excess exemplars from group {group_id}"
                )
        except Exception as exc:
            logger.debug(f"[ExemplarLibrary] Eviction failed: {exc}")

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors.

        Uses pure Python to avoid hard numpy dependency.
        """
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)
