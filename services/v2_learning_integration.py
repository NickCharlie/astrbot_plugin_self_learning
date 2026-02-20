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

from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger

from ..config import PluginConfig
from ..core.interfaces import MessageData
from ..services.tiered_learning_trigger import (
    BatchTriggerPolicy,
    TieredLearningTrigger,
    TriggerResult,
)


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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all active v2 modules that expose a ``start`` method."""
        modules: List[Tuple[str, Any]] = [
            ("knowledge_manager", self._knowledge_manager),
            ("memory_manager", self._memory_manager),
            ("exemplar_library", self._exemplar_library),
            ("social_analyzer", self._social_analyzer),
            ("jargon_filter", self._jargon_filter),
        ]
        for name, module in modules:
            if module and hasattr(module, "start"):
                try:
                    await module.start()
                except Exception as exc:
                    logger.warning(
                        f"[V2Integration] {name} start failed: {exc}"
                    )
        logger.info("[V2Integration] All modules started")

    async def stop(self) -> None:
        """Stop all active v2 modules and release resources."""
        modules: List[Tuple[str, Any]] = [
            ("knowledge_manager", self._knowledge_manager),
            ("memory_manager", self._memory_manager),
            ("exemplar_library", self._exemplar_library),
            ("social_analyzer", self._social_analyzer),
            ("jargon_filter", self._jargon_filter),
        ]
        for name, module in modules:
            if module and hasattr(module, "stop"):
                try:
                    await module.stop()
                except Exception as exc:
                    logger.warning(
                        f"[V2Integration] {name} stop failed: {exc}"
                    )

        if self._rerank_provider and hasattr(self._rerank_provider, "close"):
            try:
                await self._rerank_provider.close()
            except Exception as exc:
                logger.warning(f"[V2Integration] Reranker close failed: {exc}")

        logger.info("[V2Integration] All modules stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_message(
        self, message: MessageData, group_id: str
    ) -> TriggerResult:
        """Process an incoming message through the tiered trigger.

        Tier 1 operations run concurrently on every message.  Tier 2
        operations fire when their policies are satisfied.
        """
        return await self._trigger.process_message(message, group_id)

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
        reranked by relevance and only the top-k are returned.  Few-shot
        exemplars and graph stats are returned unmodified.
        """
        context: Dict[str, Any] = {}

        # --- Knowledge retrieval ---
        if self._knowledge_manager:
            try:
                if hasattr(self._knowledge_manager, "query_knowledge"):
                    ctx = await self._knowledge_manager.query_knowledge(
                        query, group_id
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

        # --- Memory retrieval ---
        if self._memory_manager:
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

        # --- Few-shot exemplars ---
        if self._exemplar_library:
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

        # --- Social graph stats (lightweight) ---
        if self._social_analyzer:
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

        # --- Reranking (optional, knowledge + memory only) ---
        if self._rerank_provider and context:
            context = await self._rerank_context(query, context, top_k)

        return context

    def get_trigger_stats(self, group_id: str) -> Dict[str, Any]:
        """Return tiered trigger statistics for a group."""
        return self._trigger.get_group_stats(group_id)

    # ------------------------------------------------------------------
    # Module factories
    # ------------------------------------------------------------------

    def _create_embedding_provider(self) -> Optional[Any]:
        """Resolve embedding provider from the framework."""
        try:
            from ..services.embedding.factory import EmbeddingProviderFactory
            return EmbeddingProviderFactory.create(self._config, self._context)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] Embedding provider unavailable: {exc}"
            )
            return None

    def _create_rerank_provider(self) -> Optional[Any]:
        """Resolve reranker provider from the framework."""
        try:
            from ..services.reranker.factory import RerankProviderFactory
            return RerankProviderFactory.create(self._config, self._context)
        except Exception as exc:
            logger.debug(f"[V2Integration] Reranker unavailable: {exc}")
            return None

    def _create_knowledge_manager(self) -> Optional[Any]:
        """Create knowledge manager based on configured engine."""
        if self._config.knowledge_engine == "lightrag":
            try:
                from ..services.lightrag_knowledge_manager import (
                    LightRAGKnowledgeManager,
                )
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
                from ..services.mem0_memory_manager import Mem0MemoryManager
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
            from ..services.exemplar_library import ExemplarLibrary
            return ExemplarLibrary(self._db, self._embedding_provider)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] ExemplarLibrary init failed: {exc}"
            )
            return None

    def _create_social_analyzer(self) -> Optional[Any]:
        """Create social graph analyzer."""
        try:
            from ..services.social_graph_analyzer import SocialGraphAnalyzer
            return SocialGraphAnalyzer(self._llm, self._db)
        except Exception as exc:
            logger.debug(
                f"[V2Integration] SocialGraphAnalyzer init failed: {exc}"
            )
            return None

    def _create_jargon_filter(self) -> Optional[Any]:
        """Create jargon statistical filter."""
        try:
            from ..services.jargon_statistical_filter import (
                JargonStatisticalFilter,
            )
            return JargonStatisticalFilter()
        except Exception as exc:
            logger.debug(
                f"[V2Integration] JargonStatisticalFilter init failed: {exc}"
            )
            return None

    # ------------------------------------------------------------------
    # Trigger wiring
    # ------------------------------------------------------------------

    def _register_trigger_operations(self) -> None:
        """Register all available modules with the tiered trigger."""

        # ---- Tier 1: per-message lightweight operations ----

        if self._jargon_filter:
            jf = self._jargon_filter

            async def _jargon_update(
                message: MessageData, group_id: str
            ) -> None:
                jf.update_from_message(message, group_id)

            self._trigger.register_tier1("jargon_stats", _jargon_update)

        if self._memory_manager:
            self._trigger.register_tier1(
                "memory", self._memory_manager.add_memory_from_message
            )

        if self._knowledge_manager:
            # Resolve the correct ingestion method name.
            if hasattr(
                self._knowledge_manager,
                "process_message_for_knowledge_graph",
            ):
                method_name = "process_message_for_knowledge_graph"
            elif hasattr(
                self._knowledge_manager, "process_message_for_knowledge"
            ):
                method_name = "process_message_for_knowledge"
            else:
                method_name = None
                logger.warning(
                    "[V2Integration] Knowledge manager has no recognised "
                    "ingestion method; knowledge tier-1 op skipped"
                )

            if method_name:
                self._trigger.register_tier1(
                    "knowledge",
                    getattr(self._knowledge_manager, method_name),
                )

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
                                candidate["term"], meaning, group_id
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

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

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
