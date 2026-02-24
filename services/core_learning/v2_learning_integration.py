"""
V2 learning integration layer.

Wires together the v2-architecture modules and provides a unified
interface for the ``MaiBotEnhancedLearningManager`` to delegate to.
When v2 features are enabled in ``PluginConfig`` the learning manager
instantiates this class and calls its ``process_message`` and
``get_enhanced_context`` methods alongside (or instead of) the legacy
code paths.

Modules orchestrated:
    * ``TieredLearningTrigger`` — per-message / batch operation scheduling
    * ``LightRAGKnowledgeManager`` — knowledge graph (replaces legacy)
    * ``Mem0MemoryManager`` — memory management (replaces legacy)
    * ``ExemplarLibrary`` — few-shot style exemplar retrieval
    * ``SocialGraphAnalyzer`` — community detection / influence ranking
    * ``JargonStatisticalFilter`` — statistical jargon pre-filter
    * ``IRerankProvider`` — cross-source context reranking

Design notes:
    - All module construction is guarded by the relevant config flags so
      that unused modules are never instantiated.
    - ``start()`` / ``stop()`` manage the full lifecycle of every active
      v2 module.
    - Each module that can fail during construction logs a warning and
      falls back gracefully (the integration layer keeps working with
      the remaining modules).
    - Thread-safe for single-event-loop asyncio usage.
"""

import asyncio
import hashlib
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger

from ...config import PluginConfig
from ...core.interfaces import MessageData
from ...utils.cache_manager import get_cache_manager
from ..monitoring.instrumentation import monitored
from ..quality import (
    BatchTriggerPolicy,
    TieredLearningTrigger,
    TriggerResult,
)

# Minimum message length to consider for LLM-heavy ingestion operations.
_MIN_INGESTION_LENGTH = 15

# Maximum buffered messages per group before force-flushing.
_INGESTION_BUFFER_MAX = 10


class V2LearningIntegration:
    """Facade that initialises, wires, and exposes v2 learning modules.

    Usage::

        v2 = V2LearningIntegration(config, llm_adapter, db_manager, context)
        await v2.start()
        result = await v2.process_message(message, group_id)
        context = await v2.get_enhanced_context("query", group_id)
        await v2.stop()
    """

    def __init__(
        self,
        config: PluginConfig,
        llm_adapter: Optional[Any] = None,
        db_manager: Optional[Any] = None,
        context: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._llm = llm_adapter
        self._db = db_manager
        self._context = context

        # --- Resolve framework providers via factories ---------------
        self._embedding_provider = self._create_embedding_provider()
        self._rerank_provider = self._create_rerank_provider()

        # --- Instantiate v2 modules ----------------------------------
        self._knowledge_manager = self._create_knowledge_manager()
        self._memory_manager = self._create_memory_manager()
        self._exemplar_library = self._create_exemplar_library()
        self._social_analyzer = self._create_social_analyzer()
        self._jargon_filter = self._create_jargon_filter()

        # --- Query result cache via CacheManager ----------------------
        self._cache = get_cache_manager()

        # --- Message buffer for batch ingestion -----------------------
        # Knowledge and memory ingestion are LLM-heavy operations and
        # must not run per-message. Instead, messages are buffered here
        # and flushed as a batch in a Tier 2 operation.
        self._ingestion_buffer: Dict[str, List[MessageData]] = defaultdict(list)

        # --- Tiered trigger ------------------------------------------
        self._trigger = TieredLearningTrigger()
        self._register_trigger_operations()

        logger.info(
            "[V2Integration] Initialised — "
            f"knowledge={self._config.knowledge_engine}, "
            f"memory={self._config.memory_engine}, "
            f"embedding={'yes' if self._embedding_provider else 'no'}, "
            f"reranker={'yes' if self._rerank_provider else 'no'}"
        )

    # Lifecycle

    async def start(self) -> None:
        """Start all active v2 modules that expose a ``start`` method."""
        modules: List[Tuple[str, Any]] = [
            ("knowledge_manager", self._knowledge_manager),
            ("memory_manager", self._memory_manager),
            ("exemplar_library", self._exemplar_library),
            ("social_analyzer", self._social_analyzer),
            ("jargon_filter", self._jargon_filter),
        ]

        async def _start_one(name: str, module: Any) -> None:
            try:
                await module.start()
            except Exception as exc:
                logger.warning(
                    f"[V2Integration] {name} start failed: {exc}"
                )

        await asyncio.gather(*(
            _start_one(name, module)
            for name, module in modules
            if module and hasattr(module, "start")
        ))
        logger.info("[V2Integration] All modules started")

    async def stop(self) -> None:
        """Stop all active v2 modules and release resources.

        Attempts to flush remaining buffered messages with a per-group
        timeout. Timed-out buffers are discarded to avoid blocking
        the shutdown sequence.
        """
        _flush_timeout = self._config.task_cancel_timeout

        for group_id in list(self._ingestion_buffer.keys()):
            try:
                await asyncio.wait_for(
                    self._flush_ingestion_buffer(group_id),
                    timeout=_flush_timeout,
                )
            except asyncio.TimeoutError:
                dropped = len(self._ingestion_buffer.pop(group_id, []))
                logger.warning(
                    f"[V2Integration] Buffer flush timeout for group "
                    f"{group_id}, dropped {dropped} messages"
                )
            except Exception as exc:
                logger.warning(
                    f"[V2Integration] Buffer flush failed on stop "
                    f"for group {group_id}: {exc}"
                )

        modules: List[Tuple[str, Any]] = [
            ("knowledge_manager", self._knowledge_manager),
            ("memory_manager", self._memory_manager),
            ("exemplar_library", self._exemplar_library),
            ("social_analyzer", self._social_analyzer),
            ("jargon_filter", self._jargon_filter),
        ]

        async def _stop_one(name: str, module: Any) -> None:
            try:
                await module.stop()
            except Exception as exc:
                logger.warning(
                    f"[V2Integration] {name} stop failed: {exc}"
                )

        async def _close_reranker() -> None:
            try:
                await self._rerank_provider.close()
            except Exception as exc:
                logger.warning(f"[V2Integration] Reranker close failed: {exc}")

        tasks = [
            _stop_one(name, module)
            for name, module in modules
            if module and hasattr(module, "stop")
        ]
        if self._rerank_provider and hasattr(self._rerank_provider, "close"):
            tasks.append(_close_reranker())

        await asyncio.gather(*tasks)
        logger.info("[V2Integration] All modules stopped")

    # Public API

    @monitored
    async def process_message(
        self, message: MessageData, group_id: str
    ) -> TriggerResult:
        """Process an incoming message through the tiered trigger.

        Tier 1 operations run concurrently on every message. Tier 2
        operations fire when their policies are satisfied.
        """
        return await self._trigger.process_message(message, group_id)

    @monitored
    async def get_enhanced_context(
        self,
        query: str,
        group_id: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Retrieve v2 enhanced context for response generation.

        Returns a dict with optional keys:
            * ``knowledge_context`` (str): Retrieved knowledge graph context.
            * ``related_memories`` (List[str]): Semantically related memories.
            * ``few_shot_examples`` (List[str]): Style exemplar texts
              (not reranked; returned as-is).
            * ``graph_stats`` (dict): Social graph summary statistics.

        When a reranker is available, knowledge and memory candidates are
        reranked by relevance and only the top-k are returned. Few-shot
        exemplars and graph stats are returned unmodified.

        Results are cached per (group_id, query_hash) with a configurable
        TTL to avoid redundant retrieval on repeated or similar queries.

        All retrieval tasks run concurrently via ``asyncio.gather`` to
        minimise total latency.
        """
        # --- Check query result cache ---
        cache_key = self._make_cache_key(query, group_id)
        cached_result = self._cache.get("context", cache_key)
        if cached_result is not None:
            logger.debug(
                f"[V2Integration] Context cache hit (group={group_id})"
            )
            return cached_result

        context: Dict[str, Any] = {}

        # --- Build concurrent retrieval tasks ---

        async def _fetch_knowledge() -> None:
            if not self._knowledge_manager:
                return
            try:
                if hasattr(self._knowledge_manager, "query_knowledge"):
                    ctx = await self._knowledge_manager.query_knowledge(
                        query, group_id,
                        mode=self._config.lightrag_query_mode,
                    )
                elif hasattr(
                    self._knowledge_manager,
                    "answer_question_with_knowledge_graph",
                ):
                    ctx = (
                        await self._knowledge_manager
                        .answer_question_with_knowledge_graph(query, group_id)
                    )
                else:
                    ctx = ""
                if ctx:
                    context["knowledge_context"] = ctx
            except Exception as exc:
                logger.debug(
                    f"[V2Integration] Knowledge retrieval failed: {exc}"
                )

        async def _fetch_memories() -> None:
            if not self._memory_manager:
                return
            try:
                memories = await self._memory_manager.get_related_memories(
                    query, group_id
                )
                if memories:
                    context["related_memories"] = memories
            except Exception as exc:
                logger.debug(
                    f"[V2Integration] Memory retrieval failed: {exc}"
                )

        async def _fetch_exemplars() -> None:
            if not self._exemplar_library:
                return
            try:
                examples = await self._exemplar_library.get_few_shot_examples(
                    query, group_id, k=top_k
                )
                if examples:
                    context["few_shot_examples"] = examples
            except Exception as exc:
                logger.debug(
                    f"[V2Integration] Exemplar retrieval failed: {exc}"
                )

        async def _fetch_graph_stats() -> None:
            if not self._social_analyzer:
                return
            try:
                stats = await self._social_analyzer.get_graph_statistics(
                    group_id
                )
                if stats and stats.get("node_count", 0) > 0:
                    context["graph_stats"] = stats
            except Exception as exc:
                logger.debug(
                    f"[V2Integration] Social graph stats failed: {exc}"
                )

        # --- Run all retrievals concurrently ---
        await asyncio.gather(
            _fetch_knowledge(),
            _fetch_memories(),
            _fetch_exemplars(),
            _fetch_graph_stats(),
        )

        # --- Conditional reranking ---
        # Only invoke the reranker when there are enough candidates to
        # justify the additional API round-trip latency.
        rerank_candidates = len(context.get("related_memories", []))
        if "knowledge_context" in context:
            rerank_candidates += 1
        min_candidates = getattr(
            self._config, "rerank_min_candidates", 3
        )
        if self._rerank_provider and rerank_candidates >= min_candidates:
            context = await self._rerank_context(query, context, top_k)

        # --- Store result in cache ---
        self._cache.set("context", cache_key, context)

        return context

    # Cache helpers

    @staticmethod
    def _make_cache_key(query: str, group_id: str) -> str:
        """Generate a compact cache key from query text and group ID."""
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()[:12]
        return f"{group_id}:{query_hash}"

    def get_trigger_stats(self, group_id: str) -> Dict[str, Any]:
        """Return tiered trigger statistics for a group."""
        return self._trigger.get_group_stats(group_id)

    # Module factories

    def _create_embedding_provider(self) -> Optional[Any]:
        """Resolve embedding provider from the framework."""
        try:
            from ..embedding.factory import EmbeddingProviderFactory
            return EmbeddingProviderFactory.create(self._config, self._context)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] Embedding provider unavailable: {exc}"
            )
            return None

    def _create_rerank_provider(self) -> Optional[Any]:
        """Resolve reranker provider from the framework."""
        try:
            from ..reranker.factory import RerankProviderFactory
            return RerankProviderFactory.create(self._config, self._context)
        except Exception as exc:
            logger.debug(f"[V2Integration] Reranker unavailable: {exc}")
            return None

    def _create_knowledge_manager(self) -> Optional[Any]:
        """Create knowledge manager based on configured engine."""
        if self._config.knowledge_engine == "lightrag":
            if not self._embedding_provider:
                logger.warning(
                    "[V2Integration] LightRAG requires an embedding provider "
                    "but none is available; knowledge engine disabled"
                )
                return None
            try:
                from ..integration import LightRAGKnowledgeManager
                return LightRAGKnowledgeManager(
                    self._config, self._llm, self._embedding_provider
                )
            except ImportError:
                logger.warning(
                    "[V2Integration] lightrag-hku not installed, "
                    "falling back to legacy knowledge engine"
                )
            except Exception as exc:
                logger.warning(
                    f"[V2Integration] LightRAG init failed: {exc}"
                )
                logger.debug(
                    "[V2Integration] LightRAG traceback:", exc_info=True
                )
        return None

    def _create_memory_manager(self) -> Optional[Any]:
        """Create memory manager based on configured engine."""
        if self._config.memory_engine == "mem0":
            try:
                from ..integration import Mem0MemoryManager
                return Mem0MemoryManager(
                    self._config, self._llm, self._embedding_provider
                )
            except ImportError:
                logger.warning(
                    "[V2Integration] mem0ai not installed, "
                    "falling back to legacy memory engine"
                )
            except Exception as exc:
                logger.warning(
                    f"[V2Integration] Mem0 init failed: {exc}"
                )
                logger.debug(
                    "[V2Integration] Mem0 traceback:", exc_info=True
                )
        return None

    def _create_exemplar_library(self) -> Optional[Any]:
        """Create exemplar library if DB and embedding are available."""
        if not self._db:
            return None
        try:
            from ..integration import ExemplarLibrary
            return ExemplarLibrary(self._db, self._embedding_provider)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] ExemplarLibrary init failed: {exc}"
            )
            return None

    def _create_social_analyzer(self) -> Optional[Any]:
        """Create social graph analyzer."""
        try:
            from ..social import SocialGraphAnalyzer
            return SocialGraphAnalyzer(self._llm, self._db)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] SocialGraphAnalyzer init failed: {exc}"
            )
            return None

    def _create_jargon_filter(self) -> Optional[Any]:
        """Create jargon statistical filter."""
        try:
            from ..jargon import JargonStatisticalFilter
            return JargonStatisticalFilter()
        except Exception as exc:
            logger.debug(
                f"[V2Integration] JargonStatisticalFilter init failed: {exc}"
            )
            return None

    # Trigger wiring

    def _register_trigger_operations(self) -> None:
        """Register all available modules with the tiered trigger.

        Architecture:
            Tier 1 (per-message, sub-millisecond):
                - jargon_stats: in-memory statistical counters
                - ingestion_buffer: append message to buffer (no I/O)
                - exemplar: embedding + DB insert (< 1s)

            Tier 2 (batch, LLM-gated, cooldown-protected):
                - ingestion_flush: batch-process buffered messages through
                  LightRAG and Mem0, amortising LLM overhead across
                  multiple messages
                - jargon: LLM-based jargon meaning inference
                - social: community detection and influence ranking

        Knowledge graph ingestion (LightRAG) and memory ingestion (Mem0)
        are intentionally registered as Tier 2 batch operations rather
        than Tier 1 per-message callbacks because they each invoke one
        or more LLM round-trips (entity extraction, fact extraction)
        that take 3-10 seconds per message. Running them per-message
        would dominate the event loop and block subsequent processing.
        """

        # ---- Tier 1: per-message lightweight operations ----

        if self._jargon_filter:
            jf = self._jargon_filter

            async def _jargon_update(
                message: MessageData, group_id: str
            ) -> None:
                jf.update_from_message(message.message, group_id, message.sender_id)

            self._trigger.register_tier1("jargon_stats", _jargon_update)

        # Buffer messages for batch ingestion (knowledge + memory).
        # This replaces the previous per-message LightRAG/Mem0 callbacks
        # with a sub-millisecond append operation.
        if self._knowledge_manager or self._memory_manager:
            buf = self._ingestion_buffer

            async def _buffer_message(
                message: MessageData, group_id: str
            ) -> None:
                if (
                    message.message
                    and len(message.message.strip()) >= _MIN_INGESTION_LENGTH
                ):
                    buf[group_id].append(message)

            self._trigger.register_tier1("ingestion_buffer", _buffer_message)

        if self._exemplar_library:
            lib = self._exemplar_library

            async def _exemplar_add(
                message: MessageData, group_id: str
            ) -> None:
                await lib.add_exemplar(
                    message.message, group_id, message.sender_id
                )

            self._trigger.register_tier1("exemplar", _exemplar_add)

        # ---- Tier 2: batch operations (LLM-heavy) ----

        # Batch ingestion: flush buffered messages through LightRAG
        # and Mem0. Fires every 5 messages or 60 seconds, whichever
        # comes first. This amortises the per-message LLM overhead
        # and reduces total API calls.
        if self._knowledge_manager or self._memory_manager:
            self._trigger.register_tier2(
                "ingestion_flush",
                self._flush_ingestion_buffer,
                BatchTriggerPolicy(
                    message_threshold=5, cooldown_seconds=60
                ),
            )

        if self._jargon_filter:
            jf2 = self._jargon_filter
            llm = self._llm
            db = self._db

            async def _jargon_batch(group_id: str) -> None:
                candidates = jf2.get_jargon_candidates(group_id, top_k=20)
                if not candidates or not llm:
                    return
                for candidate in candidates[:10]:
                    try:
                        meaning = await llm.generate_response(
                            f"Explain the slang/jargon term "
                            f"'{candidate['term']}' in the context of an "
                            f"online chat group. Return a concise definition.",
                            model_type="filter",
                        )
                        if (
                            meaning
                            and db
                            and hasattr(db, "save_or_update_jargon")
                        ):
                            await db.save_or_update_jargon(
                                group_id,
                                candidate["term"],
                                {
                                    "meaning": meaning,
                                    "raw_content": "[]",
                                    "is_jargon": True,
                                    "count": 1,
                                    "is_complete": True,
                                },
                            )
                    except Exception as exc:
                        logger.debug(
                            f"[V2Integration] Jargon inference failed "
                            f"for '{candidate['term']}': {exc}"
                        )

            self._trigger.register_tier2(
                "jargon",
                _jargon_batch,
                BatchTriggerPolicy(
                    message_threshold=20, cooldown_seconds=180
                ),
            )

        if self._social_analyzer:
            sa = self._social_analyzer

            async def _social_batch(group_id: str) -> None:
                # Execute independently so one failure does not skip the other.
                try:
                    await sa.detect_communities(group_id)
                except Exception as exc:
                    logger.debug(
                        f"[V2Integration] detect_communities failed: {exc}"
                    )
                try:
                    await sa.get_influence_ranking(group_id)
                except Exception as exc:
                    logger.debug(
                        f"[V2Integration] get_influence_ranking failed: {exc}"
                    )

            self._trigger.register_tier2(
                "social",
                _social_batch,
                BatchTriggerPolicy(
                    message_threshold=50, cooldown_seconds=600
                ),
            )

    # Batch ingestion

    async def _flush_ingestion_buffer(self, group_id: str) -> None:
        """Flush buffered messages for a group through knowledge and memory.

        Processes all buffered messages concurrently through LightRAG and
        Mem0 in a single batch operation, then clears the buffer. Messages
        within each engine are processed sequentially to avoid overwhelming
        the underlying LLM providers with concurrent requests.
        """
        messages = self._ingestion_buffer.pop(group_id, [])
        if not messages:
            return

        logger.debug(
            f"[V2Integration] Flushing ingestion buffer: "
            f"group={group_id}, count={len(messages)}"
        )

        async def _ingest_knowledge() -> None:
            if not self._knowledge_manager:
                return
            method = None
            if hasattr(
                self._knowledge_manager,
                "process_message_for_knowledge_graph",
            ):
                method = self._knowledge_manager.process_message_for_knowledge_graph
            elif hasattr(
                self._knowledge_manager, "process_message_for_knowledge"
            ):
                method = self._knowledge_manager.process_message_for_knowledge
            if not method:
                return
            for msg in messages:
                try:
                    await method(msg, group_id)
                except Exception as exc:
                    logger.debug(
                        f"[V2Integration] Knowledge ingestion failed: {exc}"
                    )

        async def _ingest_memory() -> None:
            if not self._memory_manager:
                return
            for msg in messages:
                try:
                    await self._memory_manager.add_memory_from_message(
                        msg, group_id
                    )
                except Exception as exc:
                    logger.debug(
                        f"[V2Integration] Memory ingestion failed: {exc}"
                    )

        # Run knowledge and memory ingestion concurrently across engines,
        # but sequentially within each engine to avoid provider overload.
        await asyncio.gather(
            _ingest_knowledge(),
            _ingest_memory(),
        )

    # Reranking

    @monitored
    async def _rerank_context(
        self,
        query: str,
        context: Dict[str, Any],
        top_k: int,
    ) -> Dict[str, Any]:
        """Rerank knowledge and memory candidates by relevance.

        Few-shot exemplars and graph stats are returned unmodified.
        """
        try:
            documents: List[str] = []
            sources: List[str] = []

            if "knowledge_context" in context:
                documents.append(context["knowledge_context"])
                sources.append("knowledge")

            for mem in context.get("related_memories", []):
                documents.append(mem)
                sources.append("memory")

            if not documents:
                return context

            results = await self._rerank_provider.rerank(
                query, documents, top_n=top_k
            )

            # Rebuild context with reranked order.
            reranked_memories: List[str] = []
            reranked_knowledge = ""
            for r in results:
                if r.index >= len(documents):
                    logger.debug(
                        f"[V2Integration] Reranker returned out-of-range "
                        f"index {r.index} (len={len(documents)}); skipping"
                    )
                    continue
                src = sources[r.index]
                doc = documents[r.index]
                if src == "knowledge":
                    reranked_knowledge = doc
                elif src == "memory":
                    reranked_memories.append(doc)

            if reranked_knowledge:
                context["knowledge_context"] = reranked_knowledge
            elif "knowledge_context" in context:
                del context["knowledge_context"]

            if reranked_memories:
                context["related_memories"] = reranked_memories
            elif "related_memories" in context:
                del context["related_memories"]

        except Exception as exc:
            logger.debug(
                f"[V2Integration] Reranking failed, using unranked: {exc}"
            )

        return context
