"""
Few-shot exemplar library.

Stores high-quality message examples and retrieves them via cosine
similarity for few-shot style imitation in LLM prompts.

When an ``IEmbeddingProvider`` is available, exemplars are embedded and
similarity search uses vector cosine distance. Without an embedding
provider the library degrades to recency-weighted random sampling.

Performance notes:
    - An in-memory vector index (per-group TTL cache) avoids repeated
      DB loads and JSON deserialization on every query.
    - When numpy is available, cosine similarity is computed via a single
      matrix–vector multiply (~1000x faster than the pure-Python fallback).
    - Similarity search loads at most ``_SIMILARITY_SEARCH_LIMIT`` exemplars
      (by weight desc) to bound DB I/O and memory.

Design notes:
    - Embedding vectors stored as JSON text columns for DB portability.
    - Weight field supports feedback-driven quality adjustment.
    - Thread-safe for single-event-loop asyncio usage.
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger
from sqlalchemy import case, delete, desc, select, update
from sqlalchemy.sql import func

from ...models.orm.exemplar import Exemplar
from ...utils.cache_manager import get_cache_manager
from ..monitoring.instrumentation import monitored

# Optional numpy for vectorised cosine similarity.
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False


# Minimum content length to accept as an exemplar.
_MIN_CONTENT_LENGTH = 10

# Maximum exemplars stored per group (FIFO eviction of lowest-weight).
_MAX_EXEMPLARS_PER_GROUP = 500

# Default number of few-shot examples to retrieve.
_DEFAULT_TOP_K = 5

# Maximum exemplars loaded from DB for similarity search (by weight desc).
_SIMILARITY_SEARCH_LIMIT = 100

# In-memory vector cache TTL (seconds).
_VECTOR_CACHE_TTL = 120


class ExemplarLibrary:
    """Few-shot style exemplar library.

    Usage::

        library = ExemplarLibrary(db_manager, embedding_provider)
        await library.add_exemplar("nice message", group_id, sender_id)
        examples = await library.get_few_shot_examples("query", group_id)
    """

    _schema_migrated = False # class-level flag: run migration once per process

    def __init__(self, db_manager, embedding_provider=None) -> None:
        """Initialise the exemplar library.

        Args:
            db_manager: SQLAlchemy database manager with ``get_session()``.
            embedding_provider: Optional ``IEmbeddingProvider`` for vector
                similarity search. When ``None``, falls back to
                weight-based random sampling.
        """
        self._db = db_manager
        self._embedding = embedding_provider

        # In-memory vector index per group.
        # group_id -> (timestamp, contents, vectors, weights)
        self._vector_cache: Dict[
            str, Tuple[float, List[str], Any, List[float]]
        ] = {}

    # Public API

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
        # One-time schema migration for existing tables.
        if not ExemplarLibrary._schema_migrated:
            await self._migrate_schema()
            ExemplarLibrary._schema_migrated = True

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

                # Evict excess exemplars if over capacity (before commit).
                await self._evict_excess(session, group_id)

                await session.commit()

                # Invalidate vector cache so next query picks up the new data.
                self._vector_cache.pop(group_id, None)

                return record_id

        except Exception as exc:
            logger.warning(f"[ExemplarLibrary] Failed to save exemplar: {exc}")
            return None

    @monitored
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

    @monitored
    async def get_few_shot_examples_with_ids(
        self,
        query: str,
        group_id: str,
        k: int = _DEFAULT_TOP_K,
    ) -> List[Tuple[int, str]]:
        """Retrieve exemplars with their record IDs for feedback tracking.

        Same logic as ``get_few_shot_examples`` but returns ``(id, content)``
        tuples so that callers can track which exemplars were used and
        later record helpful/harmful feedback.

        Args:
            query: The current query or context string.
            group_id: Chat group to search within.
            k: Number of exemplars to return.

        Returns:
            List of (exemplar_id, content) tuples, most relevant first.
        """
        if self._embedding:
            try:
                return await self._similarity_search_with_ids(
                    query, group_id, k
                )
            except Exception as exc:
                logger.debug(
                    f"[ExemplarLibrary] Similarity search (with IDs) "
                    f"failed, falling back: {exc}"
                )

        return await self._weight_based_search_with_ids(group_id, k)

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
                        weight=case(
                            (Exemplar.weight + delta < 0.0, 0.0),
                            else_=Exemplar.weight + delta,
                        ),
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

    async def record_helpful(self, exemplar_id: int) -> bool:
        """Increment the helpful counter for an exemplar.

        Called when a positive feedback signal is detected after using
        the exemplar in prompt generation (e.g. user continues conversation,
        sends positive response).

        Args:
            exemplar_id: Record ID of the exemplar.

        Returns:
            ``True`` if the update succeeded.
        """
        return await self._increment_feedback(exemplar_id, helpful=True)

    async def record_harmful(self, exemplar_id: int) -> bool:
        """Increment the harmful counter for an exemplar.

        Called when a negative feedback signal is detected (e.g. user
        expresses dissatisfaction, long silence after bot response).

        Args:
            exemplar_id: Record ID of the exemplar.

        Returns:
            ``True`` if the update succeeded.
        """
        return await self._increment_feedback(exemplar_id, helpful=False)

    async def record_feedback_batch(
        self, exemplar_ids: List[int], helpful: bool
    ) -> int:
        """Record the same feedback signal for multiple exemplars.

        Args:
            exemplar_ids: List of exemplar record IDs.
            helpful: ``True`` for positive feedback, ``False`` for negative.

        Returns:
            Number of records updated.
        """
        if not exemplar_ids:
            return 0
        try:
            col = Exemplar.helpful_count if helpful else Exemplar.harmful_count
            async with self._db.get_session() as session:
                stmt = (
                    update(Exemplar)
                    .where(Exemplar.id.in_(exemplar_ids))
                    .values(
                        **{col.key: col + 1},
                        updated_at=int(time.time()),
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
        except Exception as exc:
            logger.warning(
                f"[ExemplarLibrary] Batch feedback update failed: {exc}"
            )
            return 0

    async def _increment_feedback(
        self, exemplar_id: int, helpful: bool
    ) -> bool:
        """Increment helpful or harmful counter for a single exemplar."""
        try:
            col = Exemplar.helpful_count if helpful else Exemplar.harmful_count
            async with self._db.get_session() as session:
                stmt = (
                    update(Exemplar)
                    .where(Exemplar.id == exemplar_id)
                    .values(
                        **{col.key: col + 1},
                        updated_at=int(time.time()),
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        except Exception as exc:
            logger.warning(
                f"[ExemplarLibrary] Feedback update failed "
                f"(id={exemplar_id}, helpful={helpful}): {exc}"
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
                    func.sum(Exemplar.helpful_count),
                    func.sum(Exemplar.harmful_count),
                ).where(Exemplar.group_id == group_id)
                result = await session.execute(stmt)
                row = result.one_or_none()

                if row:
                    total_helpful = row[3] or 0
                    total_harmful = row[4] or 0
                    return {
                        "total_exemplars": row[0] or 0,
                        "avg_weight": round(float(row[1] or 0), 3),
                        "with_embeddings": row[2] or 0,
                        "total_helpful": total_helpful,
                        "total_harmful": total_harmful,
                    }
        except Exception as exc:
            logger.debug(f"[ExemplarLibrary] Stats query failed: {exc}")

        return {
            "total_exemplars": 0, "avg_weight": 0.0,
            "with_embeddings": 0, "total_helpful": 0, "total_harmful": 0,
        }

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

    # Internal helpers

    async def _migrate_schema(self) -> None:
        """Run one-time schema migrations for existing tables.

        Uses SQLAlchemy Inspector to detect missing columns and only
        applies migrations that are actually needed. Dialect-aware:
        handles both SQLite and MySQL/PostgreSQL.
        """
        try:
            async with self._db.get_session() as session:
                bind = session.get_bind()
                from sqlalchemy import inspect as sa_inspect, text

                def _run_migrations(sync_conn):
                    inspector = sa_inspect(sync_conn)
                    if not inspector.has_table("exemplar"):
                        return

                    existing_cols = {
                        c["name"] for c in inspector.get_columns("exemplar")
                    }
                    dialect_name = sync_conn.dialect.name

                    # Migration 1: Add helpful_count if missing
                    if "helpful_count" not in existing_cols:
                        sync_conn.execute(text(
                            "ALTER TABLE exemplar "
                            "ADD COLUMN helpful_count INTEGER NOT NULL DEFAULT 0"
                        ))

                    # Migration 2: Add harmful_count if missing
                    if "harmful_count" not in existing_cols:
                        sync_conn.execute(text(
                            "ALTER TABLE exemplar "
                            "ADD COLUMN harmful_count INTEGER NOT NULL DEFAULT 0"
                        ))

                    # Migration 3: MySQL-specific MEDIUMTEXT upgrade
                    if dialect_name == "mysql":
                        try:
                            sync_conn.execute(text(
                                "ALTER TABLE exemplar "
                                "MODIFY COLUMN embedding_json MEDIUMTEXT"
                            ))
                        except Exception:
                            pass

                await session.run_sync(
                    lambda sync_session: _run_migrations(
                        sync_session.connection()
                    )
                )
                await session.commit()
                logger.info(
                    "[ExemplarLibrary] Schema migration check completed"
                )
        except Exception as exc:
            logger.debug(
                f"[ExemplarLibrary] Schema migration skipped: {exc}"
            )

    async def _similarity_search(
        self, query: str, group_id: str, k: int
    ) -> List[str]:
        """Vector cosine similarity search with in-memory caching.

        Query embeddings are cached via CacheManager to avoid redundant
        embedding API calls for repeated or identical queries.
        """
        cache = get_cache_manager()
        cache_key = f"exemplar:{query[:80]}"
        query_vec = cache.get("embedding_query", cache_key)
        if query_vec is None:
            query_vec = await self._embedding.get_embedding(query)
            cache.set("embedding_query", cache_key, query_vec)

        # Use cached vectors or load from DB.
        cached = self._vector_cache.get(group_id)
        if cached and time.time() - cached[0] < _VECTOR_CACHE_TTL:
            contents, vectors, weights = cached[1], cached[2], cached[3]
        else:
            contents, vectors, weights = await self._load_vectors(group_id)
            if not contents:
                return await self._weight_based_search(group_id, k)
            self._vector_cache[group_id] = (
                time.time(), contents, vectors, weights,
            )

        if not contents:
            return await self._weight_based_search(group_id, k)

        # Numpy-accelerated path.
        if _HAS_NUMPY and isinstance(vectors, np.ndarray):
            scores = self._numpy_cosine_scores(query_vec, vectors, weights)
            top_k = min(k, len(contents))
            top_indices = np.argsort(scores)[-top_k:][::-1]
            return [contents[i] for i in top_indices]

        # Pure Python fallback.
        scored = []
        for content, vec, weight in zip(contents, vectors, weights):
            sim = self._cosine_similarity(query_vec, vec)
            score = sim * 0.8 + (weight or 1.0) * 0.2
            scored.append((content, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:k]]

    async def _load_vectors(
        self, group_id: str
    ) -> Tuple[List[str], Any, List[float]]:
        """Load exemplar vectors from DB and build an in-memory index.

        The effective weight blends the base weight with the effectiveness
        ratio derived from helpful/harmful feedback counters. This ensures
        that exemplars with strong positive feedback rank higher in
        similarity searches.

        Returns:
            ``(contents, vectors, effective_weights)`` where *vectors* is
            a numpy matrix (N, D) when numpy is available, or a list of
            lists otherwise. Returns empty lists if no data.
        """
        async with self._db.get_session() as session:
            stmt = (
                select(
                    Exemplar.content,
                    Exemplar.embedding_json,
                    Exemplar.weight,
                    Exemplar.helpful_count,
                    Exemplar.harmful_count,
                )
                .where(
                    Exemplar.group_id == group_id,
                    Exemplar.embedding_json.isnot(None),
                )
                .order_by(desc(Exemplar.weight))
                .limit(_SIMILARITY_SEARCH_LIMIT)
            )
            result = await session.execute(stmt)
            rows = result.all()

        if not rows:
            return [], None, []

        contents: List[str] = []
        raw_vectors: List[List[float]] = []
        weights: List[float] = []
        for content, emb_json, weight, helpful, harmful in rows:
            try:
                vec = json.loads(emb_json)
                contents.append(content)
                raw_vectors.append(vec)
                # Blend base weight with Laplace-smoothed effectiveness ratio
                h = helpful or 0
                m = harmful or 0
                effectiveness = (h + 1) / (h + m + 2)
                weights.append((weight or 1.0) * effectiveness)
            except (json.JSONDecodeError, TypeError):
                continue

        if not contents:
            return [], None, []

        if _HAS_NUMPY:
            matrix = np.array(raw_vectors, dtype=np.float32)
            return contents, matrix, weights

        return contents, raw_vectors, weights

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

    async def _similarity_search_with_ids(
        self, query: str, group_id: str, k: int
    ) -> List[Tuple[int, str]]:
        """Similarity search returning (id, content) tuples for tracking."""
        cache = get_cache_manager()
        cache_key = f"exemplar:{query[:80]}"
        query_vec = cache.get("embedding_query", cache_key)
        if query_vec is None:
            query_vec = await self._embedding.get_embedding(query)
            cache.set("embedding_query", cache_key, query_vec)

        ids, contents, vectors, weights = await self._load_vectors_with_ids(
            group_id
        )
        if not contents:
            return await self._weight_based_search_with_ids(group_id, k)

        if _HAS_NUMPY and isinstance(vectors, np.ndarray):
            scores = self._numpy_cosine_scores(query_vec, vectors, weights)
            top_k = min(k, len(contents))
            top_indices = np.argsort(scores)[-top_k:][::-1]
            return [(ids[i], contents[i]) for i in top_indices]

        scored = []
        for idx, (eid, content, vec, weight) in enumerate(
            zip(ids, contents, vectors, weights)
        ):
            sim = self._cosine_similarity(query_vec, vec)
            score = sim * 0.8 + (weight or 1.0) * 0.2
            scored.append((eid, content, score))
        scored.sort(key=lambda x: x[2], reverse=True)
        return [(eid, c) for eid, c, _ in scored[:k]]

    async def _weight_based_search_with_ids(
        self, group_id: str, k: int
    ) -> List[Tuple[int, str]]:
        """Fallback: return highest-weight exemplars with IDs."""
        try:
            async with self._db.get_session() as session:
                stmt = (
                    select(Exemplar.id, Exemplar.content)
                    .where(Exemplar.group_id == group_id)
                    .order_by(
                        desc(Exemplar.weight), desc(Exemplar.created_at)
                    )
                    .limit(k)
                )
                result = await session.execute(stmt)
                return [(row[0], row[1]) for row in result.all()]
        except Exception as exc:
            logger.debug(
                f"[ExemplarLibrary] Weight search (with IDs) failed: {exc}"
            )
            return []

    async def _load_vectors_with_ids(
        self, group_id: str
    ) -> Tuple[List[int], List[str], Any, List[float]]:
        """Load exemplar vectors including record IDs for tracking.

        Returns:
            ``(ids, contents, vectors, effective_weights)``
        """
        async with self._db.get_session() as session:
            stmt = (
                select(
                    Exemplar.id,
                    Exemplar.content,
                    Exemplar.embedding_json,
                    Exemplar.weight,
                    Exemplar.helpful_count,
                    Exemplar.harmful_count,
                )
                .where(
                    Exemplar.group_id == group_id,
                    Exemplar.embedding_json.isnot(None),
                )
                .order_by(desc(Exemplar.weight))
                .limit(_SIMILARITY_SEARCH_LIMIT)
            )
            result = await session.execute(stmt)
            rows = result.all()

        if not rows:
            return [], [], None, []

        ids: List[int] = []
        contents: List[str] = []
        raw_vectors: List[List[float]] = []
        weights: List[float] = []
        for eid, content, emb_json, weight, helpful, harmful in rows:
            try:
                vec = json.loads(emb_json)
                ids.append(eid)
                contents.append(content)
                raw_vectors.append(vec)
                h = helpful or 0
                m = harmful or 0
                effectiveness = (h + 1) / (h + m + 2)
                weights.append((weight or 1.0) * effectiveness)
            except (json.JSONDecodeError, TypeError):
                continue

        if not contents:
            return [], [], None, []

        if _HAS_NUMPY:
            matrix = np.array(raw_vectors, dtype=np.float32)
            return ids, contents, matrix, weights

        return ids, contents, raw_vectors, weights

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
                logger.debug(
                    f"[ExemplarLibrary] Evicted {len(ids_to_delete)} "
                    f"excess exemplars from group {group_id}"
                )
        except Exception as exc:
            logger.debug(f"[ExemplarLibrary] Eviction failed: {exc}")

    # Cosine similarity helpers

    @staticmethod
    def _numpy_cosine_scores(
        query_vec: List[float],
        matrix: "np.ndarray",
        weights: List[float],
    ) -> "np.ndarray":
        """Vectorised cosine similarity blended with quality weights.

        Computes ``score = cosine_sim * 0.8 + weight * 0.2`` for all
        rows in a single matrix–vector multiply.
        """
        query_np = np.array(query_vec, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        if query_norm < 1e-10:
            return np.zeros(len(weights), dtype=np.float32)

        row_norms = np.linalg.norm(matrix, axis=1)
        safe_norms = np.maximum(row_norms, 1e-10)
        sims = (matrix @ query_np) / (safe_norms * query_norm)

        weight_arr = np.array(weights, dtype=np.float32)
        return sims * 0.8 + weight_arr * 0.2

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
