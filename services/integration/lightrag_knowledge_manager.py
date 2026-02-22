"""
LightRAG-based knowledge manager.

Replaces the legacy ``KnowledgeGraphManager`` by using the LightRAG library
for entity/relation extraction, vector-indexed graph storage, and hybrid
retrieval. When ``knowledge_engine`` is set to ``"lightrag"`` in the plugin
config, this module is activated instead of the SQL-based implementation.

Design notes:
    - One ``LightRAG`` instance per group (data isolation via working_dir).
    - LLM and embedding calls are bridged to the existing framework adapters
      so that no additional API keys are required.
    - Query uses ``only_need_context=True`` to return raw context without
      an internal LLM QA step, reducing latency to pure retrieval time.
    - Graceful import guard: if ``lightrag`` is not installed the class
      raises a clear ``ImportError`` at construction time rather than at
      module import, so the rest of the plugin can still load under the
      ``"legacy"`` engine setting.
    - All public methods mirror the ``KnowledgeGraphManager`` interface to
      allow transparent config-based switching.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ...config import PluginConfig
from ...core.interfaces import MessageData, ServiceLifecycle
from ..embedding.base import IEmbeddingProvider
from ..monitoring.instrumentation import monitored

# Lazy import guard -- LightRAG is an optional dependency.
_LIGHTRAG_AVAILABLE = False
try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc

    _LIGHTRAG_AVAILABLE = True
except ImportError:
    LightRAG = None # type: ignore[assignment,misc]
    QueryParam = None # type: ignore[assignment,misc]
    EmbeddingFunc = None # type: ignore[assignment,misc]


class LightRAGKnowledgeManager:
    """Knowledge manager backed by the LightRAG library.

    Public interface intentionally mirrors ``KnowledgeGraphManager`` so that
    the learning manager can swap implementations via configuration:

    * ``process_message_for_knowledge_graph(message, group_id)``
    * ``query_knowledge(query, group_id)``
    * ``answer_question_with_knowledge_graph(question, group_id)``
    * ``query_knowledge_graph(query, group_id, limit)``
    * ``get_knowledge_graph_statistics(group_id)``
    * ``start()`` / ``stop()``

    Usage::

        manager = LightRAGKnowledgeManager(config, llm_adapter, embedding)
        await manager.start()
        await manager.process_message_for_knowledge_graph(msg, "group1")
        context = await manager.query_knowledge("topic", "group1")
        await manager.stop()
    """

    def __init__(
        self,
        config: PluginConfig,
        llm_adapter,
        embedding_provider: Optional[IEmbeddingProvider] = None,
    ) -> None:
        if not _LIGHTRAG_AVAILABLE:
            raise ImportError(
                "lightrag-hku is required for the LightRAG knowledge engine. "
                "Install via: pip install lightrag-hku"
            )

        self._config = config
        self._llm = llm_adapter
        self._embedding = embedding_provider
        self._status = ServiceLifecycle.CREATED

        # Per-group LightRAG instances (lazy-initialised).
        self._instances: Dict[str, LightRAG] = {}

        # Per-group initialisation locks to prevent concurrent creation.
        self._init_locks: Dict[str, asyncio.Lock] = {}

        # Base directory for all LightRAG data.
        self._base_dir = os.path.join(config.data_dir, "lightrag")

        # Track processed message counts per group for statistics.
        self._processed_counts: Dict[str, int] = {}

        # Statistics cache to avoid repeated GraphML parsing (TTL 5 minutes).
        self._stats_cache: Dict[str, tuple] = {}
        self._stats_cache_ttl: float = 300.0

    # Lifecycle

    async def start(self) -> bool:
        """Start the knowledge manager service."""
        self._status = ServiceLifecycle.RUNNING
        logger.info("[LightRAG] Knowledge manager started")
        return True

    async def stop(self) -> bool:
        """Stop the service and release all LightRAG storage handles."""
        self._status = ServiceLifecycle.STOPPING

        # Snapshot to avoid RuntimeError from dict mutation during iteration.
        instances_snapshot = list(self._instances.items())
        self._instances.clear()

        for group_id, rag in instances_snapshot:
            try:
                await rag.finalize_storages()
                logger.debug(
                    f"[LightRAG] Finalized storages for group {group_id}"
                )
            except Exception as exc:
                logger.warning(
                    f"[LightRAG] Error finalizing group {group_id}: {exc}"
                )

        self._init_locks.clear()
        self._status = ServiceLifecycle.STOPPED
        logger.info("[LightRAG] Knowledge manager stopped")
        return True

    # Public API

    async def process_message_for_knowledge_graph(
        self, message: MessageData, group_id: str
    ) -> None:
        """Extract entities/relations from a message and insert into the graph.

        This is the primary entry point, matching the legacy
        ``KnowledgeGraphManager.process_message_for_knowledge_graph`` name
        for drop-in compatibility.
        """
        if not message.message or len(message.message.strip()) < 10:
            return

        text = f"[{message.sender_name}]: {message.message}"
        try:
            rag = await self._get_rag(group_id)
            await rag.ainsert(text)
            self._processed_counts[group_id] = (
                self._processed_counts.get(group_id, 0) + 1
            )
        except Exception as exc:
            logger.warning(
                f"[LightRAG] Insert failed for group {group_id}: {exc}"
            )

    async def process_message_for_knowledge(
        self, message: MessageData, group_id: str
    ) -> None:
        """Short alias for ``process_message_for_knowledge_graph``."""
        await self.process_message_for_knowledge_graph(message, group_id)

    @monitored
    async def query_knowledge(
        self,
        query: str,
        group_id: str,
        mode: str = "hybrid",
        top_k: int = 10,
    ) -> str:
        """Retrieve knowledge context for a query without LLM QA.

        Args:
            query: The user query or topic.
            group_id: Chat group to search within.
            mode: LightRAG query mode (``naive``, ``local``, ``global``,
                ``hybrid``, ``mix``).
            top_k: Number of top items to retrieve.

        Returns:
            Retrieved context string. Empty string if nothing relevant.
        """
        try:
            rag = await self._get_rag(group_id)
            result = await rag.aquery(
                query,
                param=QueryParam(
                    mode=mode,
                    only_need_context=True,
                    top_k=top_k,
                ),
            )
            if isinstance(result, dict):
                # When only_need_context=True, LightRAG may return a dict
                # with context sections. Flatten to a single string.
                parts = []
                for key in ("entities", "relationships", "chunks"):
                    if key in result and result[key]:
                        parts.append(str(result[key]))
                return "\n\n".join(parts) if parts else ""
            return str(result) if result else ""
        except Exception as exc:
            logger.warning(
                f"[LightRAG] Query failed for group {group_id}: {exc}"
            )
            return ""

    @monitored
    async def answer_question_with_knowledge_graph(
        self,
        question: str,
        group_id: str,
    ) -> str:
        """Return retrieved context for the given question.

        Behavioural difference from the legacy ``KnowledgeGraphManager``:
        this method returns an empty string when no relevant context exists,
        rather than a fallback natural-language reply like "I don't know".
        The raw context is intended for inclusion in the main generation
        prompt, saving an LLM round-trip. Callers must handle the
        empty-string case.
        """
        return await self.query_knowledge(question, group_id)

    async def query_knowledge_graph(
        self,
        query: str,
        group_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Legacy-compatible structured query.

        Returns a list of result dicts with ``text`` and ``source`` keys.
        """
        context = await self.query_knowledge(query, group_id, top_k=limit)
        if not context:
            return []
        # Wrap the flat text into the expected list-of-dicts format.
        return [{"text": context, "source": "lightrag", "relevance": 1.0}]

    async def get_knowledge_graph_statistics(
        self, group_id: str
    ) -> Dict[str, Any]:
        """Return summary statistics for a group's knowledge graph.

        Results are cached for ``_stats_cache_ttl`` seconds to avoid
        repeatedly parsing the GraphML file on frequent status queries.
        """
        # Check TTL cache first
        if group_id in self._stats_cache:
            cached_ts, cached_stats = self._stats_cache[group_id]
            if time.time() - cached_ts < self._stats_cache_ttl:
                return cached_stats

        stats: Dict[str, Any] = {
            "engine": "lightrag",
            "entity_count": 0,
            "relation_count": 0,
            "processed_messages": self._processed_counts.get(group_id, 0),
        }

        if group_id not in self._instances:
            return stats

        working_dir = os.path.join(self._base_dir, group_id)
        graph_file = os.path.join(
            working_dir, "graph_chunk_entity_relation.graphml"
        )
        if not os.path.isfile(graph_file):
            return stats

        try:
            import networkx as nx
        except ImportError:
            logger.warning(
                "[LightRAG] networkx is not installed; "
                "entity/relation counts unavailable"
            )
            return stats

        try:
            graph = nx.read_graphml(graph_file)
            stats["entity_count"] = graph.number_of_nodes()
            stats["relation_count"] = graph.number_of_edges()
        except Exception as exc:
            logger.warning(f"[LightRAG] Could not read graph stats: {exc}")

        self._stats_cache[group_id] = (time.time(), stats)
        return stats

    # Internal helpers

    async def _get_rag(self, group_id: str) -> LightRAG:
        """Return the LightRAG instance for *group_id*, creating if needed.

        Uses a per-group asyncio lock to prevent concurrent initialisation
        of the same group (TOCTOU race).
        """
        if group_id in self._instances:
            return self._instances[group_id]

        # Retrieve or create the lock (dict key assignment is atomic in
        # CPython's GIL, so no race on the lock creation itself).
        if group_id not in self._init_locks:
            self._init_locks[group_id] = asyncio.Lock()

        async with self._init_locks[group_id]:
            # Re-check after acquiring the lock.
            if group_id in self._instances:
                return self._instances[group_id]

            working_dir = os.path.join(self._base_dir, group_id)
            os.makedirs(working_dir, exist_ok=True)

            rag_kwargs: Dict[str, Any] = {
                "working_dir": working_dir,
                "llm_model_func": self._make_llm_func(),
                "chunk_token_size": 1200,
                "chunk_overlap_token_size": 100,
                "entity_extract_max_gleaning": 1,
            }

            # Attach embedding function -- required for vector storage.
            if not self._embedding:
                raise RuntimeError(
                    "embedding_func is required for LightRAG vector storage "
                    "but no embedding provider was configured. "
                    "Please configure an embedding provider or disable "
                    "the LightRAG knowledge engine."
                )
            rag_kwargs["embedding_func"] = EmbeddingFunc(
                embedding_dim=self._embedding.get_dim(),
                max_token_size=8192,
                func=self._make_embedding_func(),
            )

            rag = LightRAG(**rag_kwargs)
            await rag.initialize_storages()
            if hasattr(rag, "initialize_pipeline_status"):
                await rag.initialize_pipeline_status()

            self._instances[group_id] = rag
            logger.info(
                f"[LightRAG] Initialised instance for group {group_id}"
            )
            return rag

    def _make_llm_func(self):
        """Build an async callable matching LightRAG's LLM function signature.

        LightRAG expects::

            async def func(
                prompt: str,
                system_prompt: str | None = None,
                history_messages: list = [],
                keyword_extraction: bool = False,
                **kwargs,
            ) -> str

        Note: ``history_messages`` is accepted but not forwarded because
        the current ``FrameworkLLMAdapter`` does not support multi-turn
        context. A debug log is emitted when history is discarded.
        """
        llm = self._llm

        async def _llm_bridge(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: Optional[list] = None,
            keyword_extraction: bool = False,
            **kwargs,
        ) -> str:
            if history_messages is None:
                history_messages = []

            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            if history_messages:
                logger.debug(
                    "[LightRAG] LLM bridge received %d history messages; "
                    "the current adapter does not forward conversation "
                    "history.",
                    len(history_messages),
                )

            result = await llm.generate_response(
                full_prompt,
                model_type="filter",
            )
            return result or ""

        return _llm_bridge

    def _make_embedding_func(self):
        """Build an async callable matching LightRAG's embedding function.

        LightRAG expects the return value to be a **numpy array** (it
        accesses ``result.size`` internally). Our ``IEmbeddingProvider``
        returns ``list[list[float]]``, so we convert here.

        The bridge accepts ``**kwargs`` because LightRAG callers may
        pass extra keyword arguments such as ``_priority`` (query path)
        that are irrelevant to the actual embedding computation.
        """
        import numpy as np

        embedding = self._embedding

        async def _embedding_bridge(texts: list, **kwargs) -> "np.ndarray":
            result = await embedding.get_embeddings(texts)
            return np.array(result, dtype=np.float32)

        return _embedding_bridge
