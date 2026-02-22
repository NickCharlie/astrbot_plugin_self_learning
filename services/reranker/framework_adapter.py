"""
Framework reranker adapter.

Thin adapter wrapping AstrBot's ``RerankProvider`` behind the plugin's
``IRerankProvider`` interface.  Translates framework ``RerankResult``
to the plugin's own dataclass to avoid tight coupling.
"""

from typing import List, Optional

from astrbot.api import logger
from astrbot.core.provider.provider import RerankProvider as FrameworkRerankProvider
from astrbot.core.provider.entities import RerankResult as FrameworkRerankResult

from .base import IRerankProvider, RerankResult, RerankProviderError
from ..monitoring.instrumentation import monitored

# Most rerank APIs enforce a query length limit (typically 256-512 tokens).
# Truncate long queries to avoid "Query is too long" errors.
_MAX_QUERY_CHARS = 512


class FrameworkRerankAdapter(IRerankProvider):
    """Adapter bridging AstrBot ``RerankProvider`` → plugin ``IRerankProvider``.

    Args:
        provider: A fully-initialised AstrBot ``RerankProvider`` instance.
    """

    def __init__(self, provider: FrameworkRerankProvider) -> None:
        if provider is None:
            raise ValueError("provider must not be None")
        self._provider = provider

    @monitored
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
    ) -> List[RerankResult]:
        try:
            # Truncate query to prevent "Query is too long" API errors.
            if len(query) > _MAX_QUERY_CHARS:
                logger.debug(
                    f"[RerankAdapter] Truncating query from {len(query)} "
                    f"to {_MAX_QUERY_CHARS} chars"
                )
                query = query[:_MAX_QUERY_CHARS]

            framework_results: List[FrameworkRerankResult] = (
                await self._provider.rerank(query, documents, top_n)
            )
            return [
                RerankResult(
                    index=r.index,
                    relevance_score=r.relevance_score,
                )
                for r in framework_results
            ]
        except Exception as exc:
            raise RerankProviderError(
                f"Framework rerank call failed: {exc}"
            ) from exc

    def get_model_name(self) -> str:
        return self._provider.get_model()

    async def close(self) -> None:
        # Framework manages its own provider lifecycle; nothing to release.
        pass

    @property
    def provider_id(self) -> str:
        """Return the framework provider's unique identifier."""
        try:
            return self._provider.meta().id
        except (ValueError, KeyError):
            return "<unknown>"
