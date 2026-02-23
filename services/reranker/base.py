"""
Reranker provider interface and value objects.

Defines the abstract contract for document reranking, aligned with
AstrBot framework's ``RerankProvider`` interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class RerankResult:
    """Single reranking result.

    Attributes:
        index: Original index in the candidate document list.
        relevance_score: Relevance score assigned by the reranker.
    """

    index: int
    relevance_score: float


class IRerankProvider(ABC):
    """Abstract reranker provider interface.

    Method signatures are aligned with AstrBot framework's
    ``RerankProvider`` to allow zero-transformation delegation.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
    ) -> List[RerankResult]:
        """Rerank documents by relevance to the query.

        Args:
            query: The query string.
            documents: List of candidate document texts.
            top_n: Maximum number of results to return.
                If ``None``, returns all documents ranked.

        Returns:
            Sorted list of ``RerankResult`` (highest relevance first).

        Raises:
            RerankProviderError: On provider communication failure.
        """

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string."""

    async def close(self) -> None:
        """Release any resources held by the provider.

        Default implementation is a no-op.
        """


class RerankProviderError(Exception):
    """Raised when a reranker provider encounters an unrecoverable error."""
