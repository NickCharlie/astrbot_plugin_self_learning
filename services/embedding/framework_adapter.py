"""
Framework embedding adapter.

Thin adapter that wraps AstrBot's ``EmbeddingProvider`` instance behind the
plugin's ``IEmbeddingProvider`` interface.  All heavy lifting (HTTP calls,
batching, retries, connection pooling) is delegated to the framework provider.

Usage::

    from astrbot.core.provider.provider import EmbeddingProvider

    framework_provider: EmbeddingProvider = context.get_provider_by_id(pid)
    adapter = FrameworkEmbeddingAdapter(framework_provider)
    vec = await adapter.get_embedding("hello world")
"""

from typing import List

from astrbot.api import logger
from astrbot.core.provider.provider import EmbeddingProvider

from .base import IEmbeddingProvider, EmbeddingProviderError


class FrameworkEmbeddingAdapter(IEmbeddingProvider):
    """Adapter bridging AstrBot ``EmbeddingProvider`` → plugin ``IEmbeddingProvider``.

    This class owns no HTTP resources; it simply delegates to the framework
    provider instance which manages its own lifecycle.

    Args:
        provider: A fully-initialised AstrBot ``EmbeddingProvider`` instance.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        if provider is None:
            raise ValueError("provider must not be None")
        self._provider = provider

    # ------------------------------------------------------------------
    # IEmbeddingProvider implementation
    # ------------------------------------------------------------------

    async def get_embedding(self, text: str) -> List[float]:
        try:
            return await self._provider.get_embedding(text)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Framework embedding call failed: {exc}"
            ) from exc

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("texts must be a non-empty list")
        try:
            return await self._provider.get_embeddings(texts)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Framework batch embedding call failed: {exc}"
            ) from exc

    def get_dim(self) -> int:
        return self._provider.get_dim()

    def get_model_name(self) -> str:
        return self._provider.get_model()

    async def close(self) -> None:
        # Framework manages its own provider lifecycle; nothing to release.
        pass

    # ------------------------------------------------------------------
    # Extended helpers (delegated to framework)
    # ------------------------------------------------------------------

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
