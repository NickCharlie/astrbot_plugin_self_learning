"""
Framework embedding adapter.

Thin adapter that wraps AstrBot's ``EmbeddingProvider`` instance behind the
plugin's ``IEmbeddingProvider`` interface. All heavy lifting (HTTP calls,
batching, retries, connection pooling) is delegated to the framework provider.

Includes a per-text TTL cache so that repeated embedding requests for the
same text (common across ExemplarLibrary, LightRAG, etc.) hit memory instead
of the remote API.

Usage::

    from astrbot.core.provider.provider import EmbeddingProvider

    framework_provider: EmbeddingProvider = context.get_provider_by_id(pid)
    adapter = FrameworkEmbeddingAdapter(framework_provider)
    vec = await adapter.get_embedding("hello world")
"""

import asyncio
import time
from typing import Dict, List, Tuple

from astrbot.api import logger
from astrbot.core.provider.provider import EmbeddingProvider

from .base import IEmbeddingProvider, EmbeddingProviderError
from ..monitoring.instrumentation import monitored

# Embedding cache parameters.
_CACHE_TTL = 300  # seconds (5 minutes)
_MAX_CACHE_SIZE = 500


class FrameworkEmbeddingAdapter(IEmbeddingProvider):
    """Adapter bridging AstrBot ``EmbeddingProvider`` -> plugin ``IEmbeddingProvider``.

    This class owns no HTTP resources; it simply delegates to the framework
    provider instance which manages its own lifecycle.

    Args:
        provider: A fully-initialised AstrBot ``EmbeddingProvider`` instance.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        if provider is None:
            raise ValueError("provider must not be None")
        self._provider = provider
        # Per-text TTL cache: text -> (timestamp, vector).
        self._embed_cache: Dict[str, Tuple[float, List[float]]] = {}
        # In-flight request deduplication: text -> Future.
        # Prevents concurrent calls for the same text from each making
        # a separate API request.
        self._inflight: Dict[str, asyncio.Future] = {}

    # IEmbeddingProvider implementation

    @monitored
    async def get_embedding(self, text: str) -> List[float]:
        cached = self._embed_cache.get(text)
        if cached:
            ts, vec = cached
            if time.time() - ts < _CACHE_TTL:
                return vec
            del self._embed_cache[text]

        # Request coalescing: if another coroutine is already fetching this
        # exact text, wait on the same future instead of issuing a second call.
        if text in self._inflight:
            return await self._inflight[text]

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[text] = fut

        try:
            # Route through the batch API which is ~20x faster than the
            # single-text provider path on most framework backends.
            vecs = await self._provider.get_embeddings([text])
            vec = vecs[0]
        except Exception as exc:
            fut.set_exception(EmbeddingProviderError(
                f"Framework embedding call failed: {exc}"
            ))
            raise EmbeddingProviderError(
                f"Framework embedding call failed: {exc}"
            ) from exc
        else:
            fut.set_result(vec)
        finally:
            self._inflight.pop(text, None)

        self._cache_put(text, vec)
        return vec

    @monitored
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("texts must be a non-empty list")

        now = time.time()
        results: List[List[float] | None] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(texts):
            cached = self._embed_cache.get(text)
            if cached and now - cached[0] < _CACHE_TTL:
                results[i] = cached[1]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            try:
                new_vecs = await self._provider.get_embeddings(uncached_texts)
            except Exception as exc:
                raise EmbeddingProviderError(
                    f"Framework batch embedding call failed: {exc}"
                ) from exc
            for idx, text, vec in zip(uncached_indices, uncached_texts, new_vecs):
                results[idx] = vec
                self._cache_put(text, vec)

        return results  # type: ignore[return-value]

    def get_dim(self) -> int:
        return self._provider.get_dim()

    def get_model_name(self) -> str:
        return self._provider.get_model()

    async def close(self) -> None:
        # Framework manages its own provider lifecycle; nothing to release.
        pass

    # Extended helpers (delegated to framework)

    async def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 16,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> List[List[float]]:
        """Batch embedding with framework-level retry and progress tracking.

        Delegates to ``EmbeddingProvider.get_embeddings_batch`` which
        implements semaphore-controlled concurrency and exponential backoff.
        """
        try:
            return await self._provider.get_embeddings_batch(
                texts,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Framework batch embedding failed: {exc}"
            ) from exc

    @property
    def provider_id(self) -> str:
        """Return the framework provider's unique identifier."""
        try:
            return self._provider.meta().id
        except (ValueError, KeyError):
            return "<unknown>"

    # Cache helpers

    def _cache_put(self, text: str, vec: List[float]) -> None:
        """Store an embedding in the TTL cache, evicting the oldest if full."""
        if len(self._embed_cache) >= _MAX_CACHE_SIZE:
            oldest = min(self._embed_cache, key=lambda k: self._embed_cache[k][0])
            del self._embed_cache[oldest]
        self._embed_cache[text] = (time.time(), vec)
