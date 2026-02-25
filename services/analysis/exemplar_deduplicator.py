"""
Exemplar semantic deduplication service.

Inspired by the ACE BulletpointAnalyzer pattern, this service periodically
analyses the fewshot exemplar library for semantic overlap and merges
redundant entries to improve prompt information density.

Algorithm overview:
    1. Load all exemplars for a group (up to ``_DEDUP_BATCH_LIMIT``).
    2. Compute embedding vectors via ``IEmbeddingProvider.get_embeddings``.
    3. Build a pairwise cosine-similarity matrix.
    4. Cluster entries exceeding the similarity threshold via Union-Find.
    5. For each cluster, delegate merge to the LLM (or pick the
       highest-weight representative if LLM is unavailable).
    6. Persist the merged exemplar and delete the redundant ones.

Design notes:
    - Embedding is optional: when no provider is configured the service
      is a no-op, keeping the critical path unaffected.
    - Union-Find gives O(N * alpha(N)) clustering without external deps.
    - The merge LLM prompt asks for a single concise exemplar that
      preserves the stylistic essence of the cluster members.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger
from sqlalchemy import delete, desc, select, update
from sqlalchemy.sql import func

from ...models.orm.exemplar import Exemplar
from ...services.embedding.base import IEmbeddingProvider
from ...core.framework_llm_adapter import FrameworkLLMAdapter

# Optional numpy for vectorised similarity computation.
try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# Maximum exemplars loaded per deduplication pass.
_DEDUP_BATCH_LIMIT = 200

# Default cosine-similarity threshold above which two exemplars are
# considered semantically redundant.
_DEFAULT_SIMILARITY_THRESHOLD = 0.85

# Minimum cluster size that triggers an LLM merge.  Pairs (size == 2)
# are merged by picking the higher-weight exemplar to avoid unnecessary
# LLM calls.
_LLM_MERGE_MIN_CLUSTER_SIZE = 3


@dataclass
class DeduplicationResult:
    """Outcome of a deduplication pass."""

    success: bool
    original_count: int = 0
    merged_count: int = 0
    final_count: int = 0
    clusters: List[Dict[str, Any]] = field(default_factory=list)


class _UnionFind:
    """Lightweight Union-Find (disjoint-set) with path compression."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


class ExemplarDeduplicator:
    """Semantic deduplication for the fewshot exemplar library.

    Usage::

        dedup = ExemplarDeduplicator(db, embedding, llm_adapter)
        result = await dedup.deduplicate("group_123")
        if result.success:
            logger.info(f"Merged {result.merged_count} redundant exemplars")
    """

    def __init__(
        self,
        db_manager: Any,
        embedding_provider: Optional[IEmbeddingProvider] = None,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._db = db_manager
        self._embedding = embedding_provider
        self._llm = llm_adapter
        self._threshold = similarity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def deduplicate(
        self,
        group_id: str,
        threshold: Optional[float] = None,
    ) -> DeduplicationResult:
        """Run a single deduplication pass for *group_id*.

        Args:
            group_id: Chat group identifier.
            threshold: Override the configured similarity threshold.

        Returns:
            A ``DeduplicationResult`` summarising what changed.
        """
        if not self._embedding:
            logger.debug(
                "[ExemplarDedup] No embedding provider, skipping dedup"
            )
            return DeduplicationResult(success=True)

        sim_threshold = threshold if threshold is not None else self._threshold

        # Step 1 -- load exemplars.
        records = await self._load_exemplars(group_id)
        if len(records) < 2:
            return DeduplicationResult(
                success=True,
                original_count=len(records),
                final_count=len(records),
            )

        original_count = len(records)

        # Step 2 -- compute embeddings for exemplars missing vectors.
        ids, contents, vectors = await self._ensure_embeddings(records)
        if len(vectors) < 2:
            return DeduplicationResult(
                success=True,
                original_count=original_count,
                final_count=original_count,
            )

        # Step 3 -- build similarity matrix and cluster.
        clusters = self._find_clusters(vectors, sim_threshold)

        if not clusters:
            logger.debug(
                f"[ExemplarDedup] No redundant clusters in group {group_id}"
            )
            return DeduplicationResult(
                success=True,
                original_count=original_count,
                final_count=original_count,
            )

        # Step 4 -- merge each cluster.
        merged_count = 0
        cluster_details: List[Dict[str, Any]] = []

        for cluster_indices in clusters:
            cluster_ids = [ids[i] for i in cluster_indices]
            cluster_contents = [contents[i] for i in cluster_indices]

            merged_content = await self._merge_cluster(
                cluster_contents, group_id
            )
            if not merged_content:
                continue

            detail = await self._apply_merge(
                group_id, cluster_ids, cluster_contents, merged_content
            )
            if detail:
                cluster_details.append(detail)
                # Original cluster had N items, after merge 1 remains.
                merged_count += len(cluster_ids) - 1

        final_count = original_count - merged_count
        logger.info(
            f"[ExemplarDedup] Group {group_id}: "
            f"{original_count} -> {final_count} exemplars "
            f"({len(cluster_details)} clusters merged)"
        )

        return DeduplicationResult(
            success=True,
            original_count=original_count,
            merged_count=merged_count,
            final_count=final_count,
            clusters=cluster_details,
        )

    async def should_deduplicate(self, group_id: str) -> bool:
        """Return ``True`` if the group has enough exemplars to warrant
        a deduplication pass."""
        if not self._embedding:
            return False
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count(Exemplar.id)).where(
                    Exemplar.group_id == group_id
                )
                result = await session.execute(stmt)
                total = result.scalar() or 0
                return total >= 10
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_exemplars(
        self, group_id: str
    ) -> List[Tuple[int, str, Optional[str], float, int, int]]:
        """Load exemplars ordered by weight descending."""
        try:
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
                    .where(Exemplar.group_id == group_id)
                    .order_by(desc(Exemplar.weight))
                    .limit(_DEDUP_BATCH_LIMIT)
                )
                result = await session.execute(stmt)
                return list(result.all())
        except Exception as exc:
            logger.warning(
                f"[ExemplarDedup] Failed to load exemplars: {exc}"
            )
            return []

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    async def _ensure_embeddings(
        self,
        records: List[Tuple[int, str, Optional[str], float, int, int]],
    ) -> Tuple[List[int], List[str], Any]:
        """Return (ids, contents, vectors) ensuring every record has a
        vector.  Records without a stored embedding are embedded on the
        fly and persisted back to the DB."""
        ids: List[int] = []
        contents: List[str] = []
        vectors: List[List[float]] = []

        need_embedding_ids: List[int] = []
        need_embedding_texts: List[str] = []

        for eid, content, emb_json, weight, helpful, harmful in records:
            ids.append(eid)
            contents.append(content)
            if emb_json:
                try:
                    vectors.append(json.loads(emb_json))
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            # Mark for batch embedding.
            need_embedding_ids.append(eid)
            need_embedding_texts.append(content)
            vectors.append([])  # placeholder

        # Batch-embed missing vectors.
        if need_embedding_texts and self._embedding:
            try:
                new_vectors = await self._embedding.get_embeddings(
                    need_embedding_texts
                )
                id_to_vec = dict(zip(need_embedding_ids, new_vectors))

                # Backfill the placeholder slots.
                for idx, eid in enumerate(ids):
                    if eid in id_to_vec:
                        vectors[idx] = id_to_vec[eid]

                # Persist new embeddings to DB.
                await self._persist_embeddings(id_to_vec)
            except Exception as exc:
                logger.warning(
                    f"[ExemplarDedup] Batch embedding failed: {exc}"
                )
                # Drop records that still lack vectors.
                valid = [
                    (i, c, v)
                    for i, c, v in zip(ids, contents, vectors)
                    if v
                ]
                if not valid:
                    return [], [], None
                ids, contents, vectors = (
                    [t[0] for t in valid],
                    [t[1] for t in valid],
                    [t[2] for t in valid],
                )

        # Remove any remaining empty placeholders.
        valid = [
            (i, c, v) for i, c, v in zip(ids, contents, vectors) if v
        ]
        if not valid:
            return [], [], None
        ids = [t[0] for t in valid]
        contents = [t[1] for t in valid]
        raw_vectors = [t[2] for t in valid]

        if _HAS_NUMPY:
            matrix = np.array(raw_vectors, dtype=np.float32)
            return ids, contents, matrix

        return ids, contents, raw_vectors

    async def _persist_embeddings(
        self, id_to_vec: Dict[int, List[float]]
    ) -> None:
        """Write newly-computed embedding vectors back to the DB."""
        try:
            async with self._db.get_session() as session:
                for eid, vec in id_to_vec.items():
                    stmt = (
                        update(Exemplar)
                        .where(Exemplar.id == eid)
                        .values(
                            embedding_json=json.dumps(vec),
                            dimensions=len(vec),
                            updated_at=int(time.time()),
                        )
                    )
                    await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.debug(
                f"[ExemplarDedup] Embedding persistence failed: {exc}"
            )

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def _find_clusters(
        self, vectors: Any, threshold: float
    ) -> List[List[int]]:
        """Build similarity matrix and return clusters of redundant
        exemplars via Union-Find.

        Only returns clusters with 2+ members.
        """
        n = len(vectors) if not _HAS_NUMPY else vectors.shape[0]
        if n < 2:
            return []

        uf = _UnionFind(n)

        if _HAS_NUMPY and isinstance(vectors, np.ndarray):
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            safe_norms = np.maximum(norms, 1e-10)
            normalised = vectors / safe_norms
            sim_matrix = normalised @ normalised.T

            for i in range(n):
                for j in range(i + 1, n):
                    if sim_matrix[i, j] >= threshold:
                        uf.union(i, j)
        else:
            for i in range(n):
                for j in range(i + 1, n):
                    sim = self._cosine_similarity(vectors[i], vectors[j])
                    if sim >= threshold:
                        uf.union(i, j)

        # Collect clusters.
        groups: Dict[int, List[int]] = {}
        for idx in range(n):
            root = uf.find(idx)
            groups.setdefault(root, []).append(idx)

        return [members for members in groups.values() if len(members) >= 2]

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    async def _merge_cluster(
        self,
        contents: List[str],
        group_id: str,
    ) -> Optional[str]:
        """Produce a single merged exemplar from a cluster.

        For small clusters (2 items) or when no LLM is available, picks
        the longest content as representative.  Larger clusters are
        delegated to the LLM for intelligent merge.
        """
        if len(contents) < _LLM_MERGE_MIN_CLUSTER_SIZE or not self._llm:
            return self._pick_representative(contents)

        prompt = (
            "You are a style exemplar curator. The following messages are "
            "semantically similar examples used for few-shot style imitation. "
            "Merge them into a SINGLE concise message that preserves the "
            "key stylistic traits (tone, vocabulary, sentence structure).\n\n"
            "Messages to merge:\n"
        )
        for idx, text in enumerate(contents, 1):
            prompt += f"{idx}. {text}\n"
        prompt += (
            "\nReturn ONLY the merged message text, nothing else. "
            "Keep the language and register of the originals."
        )

        try:
            response = await self._llm.filter_chat_completion(prompt=prompt)
            if response and len(response.strip()) >= 5:
                return response.strip()
        except Exception as exc:
            logger.debug(f"[ExemplarDedup] LLM merge failed: {exc}")

        return self._pick_representative(contents)

    @staticmethod
    def _pick_representative(contents: List[str]) -> str:
        """Pick the longest content as the cluster representative."""
        return max(contents, key=len)

    async def _apply_merge(
        self,
        group_id: str,
        cluster_ids: List[int],
        cluster_contents: List[str],
        merged_content: str,
    ) -> Optional[Dict[str, Any]]:
        """Persist a cluster merge: update the primary record and delete
        the rest.

        The primary record (first in the list, i.e. highest-weight)
        receives the merged content and aggregated feedback counters.
        """
        if len(cluster_ids) < 2:
            return None

        primary_id = cluster_ids[0]
        redundant_ids = cluster_ids[1:]

        try:
            async with self._db.get_session() as session:
                # Aggregate counters from redundant records.
                agg_stmt = (
                    select(
                        func.sum(Exemplar.helpful_count),
                        func.sum(Exemplar.harmful_count),
                        func.max(Exemplar.weight),
                    )
                    .where(Exemplar.id.in_(cluster_ids))
                )
                agg_result = await session.execute(agg_stmt)
                agg_row = agg_result.one_or_none()

                total_helpful = (agg_row[0] or 0) if agg_row else 0
                total_harmful = (agg_row[1] or 0) if agg_row else 0
                max_weight = (agg_row[2] or 1.0) if agg_row else 1.0

                # Compute new embedding for the merged content.
                embedding_json = None
                dimensions = 0
                if self._embedding:
                    try:
                        vec = await self._embedding.get_embedding(
                            merged_content
                        )
                        embedding_json = json.dumps(vec)
                        dimensions = len(vec)
                    except Exception:
                        pass

                now = int(time.time())

                # Update the primary record.
                update_stmt = (
                    update(Exemplar)
                    .where(Exemplar.id == primary_id)
                    .values(
                        content=merged_content,
                        weight=max_weight,
                        helpful_count=total_helpful,
                        harmful_count=total_harmful,
                        embedding_json=embedding_json,
                        dimensions=dimensions,
                        updated_at=now,
                    )
                )
                await session.execute(update_stmt)

                # Delete redundant records.
                del_stmt = delete(Exemplar).where(
                    Exemplar.id.in_(redundant_ids)
                )
                await session.execute(del_stmt)
                await session.commit()

                return {
                    "primary_id": primary_id,
                    "deleted_ids": redundant_ids,
                    "merged_content": merged_content[:100],
                    "total_helpful": total_helpful,
                    "total_harmful": total_harmful,
                }

        except Exception as exc:
            logger.warning(f"[ExemplarDedup] Merge persistence failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Similarity helper (pure-Python fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(
        vec_a: List[float], vec_b: List[float]
    ) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return dot / (norm_a * norm_b)
