"""
mem0-based memory manager.

Replaces the legacy ``MemoryGraphManager`` by using the mem0 library for
automatic memory extraction, semantic vector search, and contradiction
detection. When ``memory_engine`` is set to ``"mem0"`` in the plugin
config, this module is activated instead of the NetworkX-based
implementation.

Design notes:
    - Uses mem0's built-in LLM fact extraction to distil memories from
      chat messages, replacing manual ``jieba`` concept extraction.
    - Semantic vector retrieval via Qdrant (local embedded mode, no
      external server required).
    - Group isolation achieved by using ``agent_id=group_id`` as the
      mem0 scoping parameter.
    - Embedding calls are bridged to the AstrBot framework's embedding
      provider via a custom ``EmbeddingBase`` subclass, so no separate
      embedding API credentials are needed.
    - LLM calls are bridged to the AstrBot framework's LLM provider
      via a custom ``LLMBase`` subclass, so no separate LLM API
      credentials are needed.
    - Blocking mem0 calls are offloaded to a thread pool via
      ``asyncio.to_thread`` to keep the event loop responsive.
    - Graceful import guard: if ``mem0ai`` is not installed the class
      raises a clear ``ImportError`` at construction time.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ...config import PluginConfig
from ...core.interfaces import MessageData, ServiceLifecycle
from ..monitoring.instrumentation import monitored

# Lazy import guard -- mem0ai is an optional dependency.
_MEM0_AVAILABLE = False
try:
    from mem0 import Memory as Mem0Memory
    from mem0.embeddings.base import EmbeddingBase
    from mem0.llms.base import LLMBase

    _MEM0_AVAILABLE = True
except ImportError:
    Mem0Memory = None # type: ignore[assignment,misc]
    EmbeddingBase = None # type: ignore[assignment,misc]
    LLMBase = None # type: ignore[assignment,misc]


def _create_framework_embedder(embedding_provider):
    """Build a mem0-compatible embedder that delegates to the framework.

    Returns a subclass of ``mem0.embeddings.base.EmbeddingBase`` whose
    ``embed()`` method calls the AstrBot framework's embedding provider
    directly, eliminating the need to extract API credentials.

    Because mem0 calls ``embed()`` synchronously (from within
    ``asyncio.to_thread``), we use ``asyncio.run_coroutine_threadsafe``
    to bridge back into the running event loop.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    provider = embedding_provider

    class _FrameworkEmbedder(EmbeddingBase):
        def __init__(self):
            # Skip parent __init__ to avoid BaseEmbedderConfig dependency.
            self.config = type("_Cfg", (), {
                "model": "framework",
                "embedding_dims": provider.get_dim(),
            })()

        def embed(self, text, memory_action=None):
            future = asyncio.run_coroutine_threadsafe(
                provider.get_embedding(text), loop,
            )
            return future.result(timeout=30)

    return _FrameworkEmbedder()


def _create_framework_llm(llm_adapter):
    """Build a mem0-compatible LLM that delegates to the framework.

    Returns a subclass of ``mem0.llms.base.LLMBase`` whose
    ``generate_response()`` method calls the AstrBot framework's LLM
    adapter directly, eliminating the need to extract API credentials.

    Because mem0 calls ``generate_response()`` synchronously (from within
    ``asyncio.to_thread``), we use ``asyncio.run_coroutine_threadsafe``
    to bridge back into the running event loop.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    adapter = llm_adapter

    class _FrameworkLLM(LLMBase):
        def __init__(self):
            # Skip parent __init__ to avoid BaseLlmConfig validation.
            self.config = type("_Cfg", (), {
                "model": "framework",
                "temperature": 0.1,
                "max_tokens": 2000,
                "top_p": 0.1,
            })()

        def generate_response(self, messages, tools=None, tool_choice="auto", **kwargs):
            system_prompt = None
            prompt = None
            contexts = []

            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    system_prompt = content
                else:
                    if role == "user" and prompt is not None:
                        contexts.append({"role": "user", "content": prompt})
                    if role == "user":
                        prompt = content
                    else:
                        contexts.append(msg)

            if prompt is None:
                return ""

            future = asyncio.run_coroutine_threadsafe(
                adapter.filter_chat_completion(
                    prompt=prompt,
                    contexts=contexts or None,
                    system_prompt=system_prompt,
                ),
                loop,
            )
            result = future.result(timeout=120)
            return result or ""

    return _FrameworkLLM()


class Mem0MemoryManager:
    """Memory manager backed by the mem0 library.

    Public interface mirrors ``MemoryGraphManager`` for transparent
    config-based switching:

    * ``add_memory_from_message(message, group_id)``
    * ``get_related_memories(query, group_id, limit)``
    * ``get_memory_graph_statistics(group_id)``
    * ``save_memory_graph(group_id)`` -- no-op (mem0 auto-persists)
    * ``load_memory_graph(group_id)`` -- no-op (mem0 auto-loads)
    * ``start()`` / ``stop()``

    Usage::

        manager = Mem0MemoryManager(config, llm_adapter, embedding_provider)
        await manager.start()
        await manager.add_memory_from_message(msg, "group1")
        memories = await manager.get_related_memories("topic", "group1")
        await manager.stop()
    """

    def __init__(
        self,
        config: PluginConfig,
        llm_adapter,
        embedding_provider=None,
    ) -> None:
        if not _MEM0_AVAILABLE:
            raise ImportError(
                "mem0ai is required for the mem0 memory engine. "
                "Install via: pip install mem0ai"
            )

        self._config = config
        self._llm_adapter = llm_adapter
        self._embedding_provider = embedding_provider
        self._status = ServiceLifecycle.CREATED
        self._memory: Optional[Mem0Memory] = None

        # Provide a dict-like attribute so callers iterating over
        # memory_graphs (as with the legacy manager) get an empty dict
        # instead of an AttributeError.
        self.memory_graphs: Dict[str, Any] = {}

    # Lifecycle

    async def start(self) -> bool:
        """Initialise the mem0 Memory instance.

        After construction, replaces mem0's internal LLM and embedding
        model with bridges to the framework's providers so that all
        API calls go through AstrBot's provider system.
        """
        try:
            mem0_config = self._build_config()
            self._memory = await asyncio.to_thread(
                Mem0Memory.from_config, mem0_config
            )

            # Replace mem0's LLM with framework bridge.
            if self._llm_adapter:
                self._memory.llm = _create_framework_llm(
                    self._llm_adapter
                )

            # Replace mem0's embedding model with framework bridge.
            if self._embedding_provider:
                self._memory.embedding_model = _create_framework_embedder(
                    self._embedding_provider
                )

            self._status = ServiceLifecycle.RUNNING
            logger.info("[Mem0] Memory manager started")
            return True
        except Exception as exc:
            logger.error(f"[Mem0] Failed to start: {exc}")
            self._status = ServiceLifecycle.ERROR
            return False

    async def stop(self) -> bool:
        """Release the mem0 instance."""
        self._status = ServiceLifecycle.STOPPING
        self._memory = None
        self._status = ServiceLifecycle.STOPPED
        logger.info("[Mem0] Memory manager stopped")
        return True

    # Public API

    async def add_memory_from_message(
        self, message: MessageData, group_id: str
    ) -> None:
        """Extract and store memories from an incoming message.

        mem0 automatically distils facts from the text via its LLM
        pipeline, handling deduplication and contradiction resolution.
        """
        if not self._memory:
            return

        text = self._extract_text(message)
        if not text:
            return

        try:
            await asyncio.to_thread(
                self._memory.add,
                text,
                user_id=message.sender_id,
                agent_id=group_id,
                metadata={"sender_name": message.sender_name},
            )
        except Exception as exc:
            logger.debug(f"[Mem0] add_memory failed: {exc}")

    @monitored
    async def get_related_memories(
        self,
        query: str,
        group_id: str,
        limit: int = 5,
    ) -> List[str]:
        """Retrieve semantically related memories for a group.

        Returns:
            List of memory text strings, most relevant first.
        """
        if not self._memory:
            return []

        try:
            results = await asyncio.to_thread(
                self._memory.search,
                query,
                agent_id=group_id,
                limit=limit,
            )
            # mem0 v1.1 format: {"results": [{"memory": str, ...}, ...]}
            entries = results.get("results", []) if isinstance(results, dict) else results
            return [
                entry["memory"]
                for entry in entries
                if isinstance(entry, dict) and entry.get("memory")
            ]
        except Exception as exc:
            logger.debug(f"[Mem0] search failed: {exc}")
            return []

    async def get_memory_graph_statistics(
        self, group_id: str
    ) -> Dict[str, Any]:
        """Return summary statistics for a group's memory store."""
        stats: Dict[str, Any] = {
            "engine": "mem0",
            "total_memories": 0,
        }

        if not self._memory:
            return stats

        try:
            all_memories = await asyncio.to_thread(
                self._memory.get_all,
                agent_id=group_id,
            )
            entries = (
                all_memories.get("results", [])
                if isinstance(all_memories, dict)
                else all_memories
            )
            stats["total_memories"] = len(entries) if entries else 0
        except Exception as exc:
            logger.debug(f"[Mem0] get_all failed: {exc}")

        return stats

    async def save_memory_graph(self, group_id: str) -> None:
        """No-op: mem0 auto-persists to Qdrant."""

    async def load_memory_graph(self, group_id: str) -> None:
        """No-op: mem0 auto-loads from Qdrant."""

    def get_memory_graph(self, group_id: str) -> None:
        """Compatibility stub. Returns ``None`` since mem0 does not
        expose an in-memory graph object."""
        return None

    # Internal helpers

    @staticmethod
    def _extract_text(message: MessageData) -> str:
        """Build a text representation from a MessageData instance."""
        text = getattr(message, "message", "") or ""
        text = text.strip()
        if len(text) < 5:
            return ""
        sender = getattr(message, "sender_name", "Unknown")
        return f"[{sender}]: {text}"

    def _build_config(self) -> dict:
        """Build the mem0 configuration dict.

        LLM and embedding are handled separately: after Memory creation,
        both are replaced with framework bridges (see ``start``), so no
        API credentials are needed here.
        """
        config: Dict[str, Any] = {"version": "v1.1"}

        # Provide placeholder LLM and embedder configs so Memory.__init__
        # can construct OpenAI clients without error.  Both instances are
        # replaced with framework bridges immediately after (see start()).
        config["llm"] = {
            "provider": "openai",
            "config": {
                "model": "gpt-4o-mini",
                "api_key": "placeholder-replaced-by-framework-bridge",
            },
        }
        config["embedder"] = {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": "placeholder-replaced-by-framework-bridge",
            },
        }

        # -- Vector store (local Qdrant, no external server) --
        qdrant_path = os.path.join(self._config.data_dir, "mem0_qdrant")
        os.makedirs(qdrant_path, exist_ok=True)

        embedding_dims = 1536 # default for text-embedding-3-small
        if self._embedding_provider:
            try:
                embedding_dims = self._embedding_provider.get_dim()
            except Exception:
                pass

        config["vector_store"] = {
            "provider": "qdrant",
            "config": {
                "collection_name": "self_learning_memories",
                "path": qdrant_path,
                "on_disk": True,
                "embedding_model_dims": embedding_dims,
            },
        }

        return config
