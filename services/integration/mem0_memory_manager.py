"""
mem0-based memory manager.

Replaces the legacy ``MemoryGraphManager`` by using the mem0 library for
automatic memory extraction, semantic vector search, and contradiction
detection.  When ``memory_engine`` is set to ``"mem0"`` in the plugin
config, this module is activated instead of the NetworkX-based
implementation.

Design notes:
    - Uses mem0's built-in LLM fact extraction to distil memories from
      chat messages, replacing manual ``jieba`` concept extraction.
    - Semantic vector retrieval via Qdrant (local embedded mode, no
      external server required).
    - Group isolation achieved by using ``agent_id=group_id`` as the
      mem0 scoping parameter.
    - LLM and embedding credentials are extracted from the AstrBot
      framework providers at initialisation time so users only configure
      providers once.
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

# Lazy import guard -- mem0ai is an optional dependency.
_MEM0_AVAILABLE = False
try:
    from mem0 import Memory as Mem0Memory

    _MEM0_AVAILABLE = True
except ImportError:
    Mem0Memory = None  # type: ignore[assignment,misc]


class Mem0MemoryManager:
    """Memory manager backed by the mem0 library.

    Public interface mirrors ``MemoryGraphManager`` for transparent
    config-based switching:

    * ``add_memory_from_message(message, group_id)``
    * ``get_related_memories(query, group_id, limit)``
    * ``get_memory_graph_statistics(group_id)``
    * ``save_memory_graph(group_id)``  -- no-op (mem0 auto-persists)
    * ``load_memory_graph(group_id)``  -- no-op (mem0 auto-loads)
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Initialise the mem0 Memory instance."""
        try:
            mem0_config = self._build_config()
            self._memory = await asyncio.to_thread(
                Mem0Memory.from_config, mem0_config
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        """Compatibility stub.  Returns ``None`` since mem0 does not
        expose an in-memory graph object."""
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

        Attempts to extract LLM and embedding API credentials from the
        AstrBot framework providers.  Falls back to env variables if
        extraction fails (mem0 reads ``OPENAI_API_KEY`` by default).
        """
        config: Dict[str, Any] = {"version": "v1.1"}

        # -- LLM config --
        llm_cfg = self._extract_llm_credentials()
        if llm_cfg:
            config["llm"] = llm_cfg

        # -- Embedding config --
        emb_cfg = self._extract_embedding_credentials()
        if emb_cfg:
            config["embedder"] = emb_cfg

        # -- Vector store (local Qdrant, no external server) --
        qdrant_path = os.path.join(self._config.data_dir, "mem0_qdrant")
        os.makedirs(qdrant_path, exist_ok=True)

        embedding_dims = 1536  # default for text-embedding-3-small
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

    def _extract_llm_credentials(self) -> Optional[Dict[str, Any]]:
        """Try to extract LLM API credentials from the framework adapter."""
        try:
            provider = (
                self._llm_adapter.filter_provider
                or self._llm_adapter.refine_provider
                or self._llm_adapter.reinforce_provider
            )
            if not provider:
                return None

            pc = getattr(provider, "provider_config", {})
            api_key = None
            if hasattr(provider, "get_current_key"):
                api_key = provider.get_current_key()
            if not api_key:
                keys = pc.get("key", [])
                api_key = keys[0] if keys else None

            base_url = pc.get("api_base") or None
            model = provider.get_model() if hasattr(provider, "get_model") else None

            if not api_key:
                return None

            llm_config: Dict[str, Any] = {
                "model": model or "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 1500,
                "api_key": api_key,
            }
            if base_url:
                llm_config["openai_base_url"] = base_url

            return {"provider": "openai", "config": llm_config}

        except Exception as exc:
            logger.debug(
                f"[Mem0] Could not extract LLM credentials, "
                f"using mem0 defaults: {exc}"
            )
            return None

    def _extract_embedding_credentials(self) -> Optional[Dict[str, Any]]:
        """Try to extract embedding API credentials from the framework."""
        try:
            emb = self._embedding_provider
            if not emb:
                return None

            # Unwrap the FrameworkEmbeddingAdapter to reach the underlying
            # AstrBot EmbeddingProvider which holds provider_config.
            underlying = getattr(emb, "_provider", None)
            if not underlying:
                return None

            pc = getattr(underlying, "provider_config", {})
            api_key = pc.get("embedding_api_key") or None
            base_url = pc.get("embedding_api_base") or None
            model = underlying.get_model() if hasattr(underlying, "get_model") else None

            if not api_key:
                return None

            emb_config: Dict[str, Any] = {
                "model": model or "text-embedding-3-small",
                "api_key": api_key,
            }
            if base_url:
                emb_config["openai_base_url"] = base_url

            dim = emb.get_dim() if hasattr(emb, "get_dim") else 1536
            emb_config["embedding_dims"] = dim

            return {"provider": "openai", "config": emb_config}

        except Exception as exc:
            logger.debug(
                f"[Mem0] Could not extract embedding credentials, "
                f"using mem0 defaults: {exc}"
            )
            return None
