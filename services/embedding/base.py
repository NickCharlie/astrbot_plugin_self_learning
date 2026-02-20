"""
Embedding provider interface and value objects.

Defines the abstract contract that all embedding providers must implement.
Aligned with AstrBot framework's ``EmbeddingProvider`` method signatures
to ensure seamless integration while keeping plugin-level decoupling.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class EmbeddingResult:
    """Immutable result from an embedding operation.

    Attributes:
        embeddings: List of embedding vectors, one per input text.
        model: The model identifier used for this embedding.
        dimensions: Dimensionality of each embedding vector.
        usage: Provider-specific usage metadata (e.g. token counts).
    """

    embeddings: List[List[float]]
    model: str
    dimensions: int
    usage: Dict[str, Any] = field(default_factory=dict)


class IEmbeddingProvider(ABC):
    """Abstract embedding provider interface.

    Method signatures are deliberately aligned with AstrBot framework's
    ``EmbeddingProvider`` base class (``get_embedding``, ``get_embeddings``,
    ``get_dim``) so that framework adapters can delegate with zero
    transformation.
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text.

        Args:
            text: The string to embed.

        Returns:
            A single embedding vector.

        Raises:
            EmbeddingProviderError: On provider communication failure.
        """

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            One embedding vector per input text, in the same order.

        Raises:
            ValueError: If *texts* is empty.
            EmbeddingProviderError: On provider communication failure.
        """

    @abstractmethod
    def get_dim(self) -> int:
        """Return the embedding dimensionality for the current model."""

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string."""

    async def close(self) -> None:
        """Release any resources held by the provider.

        Default implementation is a no-op.  Subclasses that manage
        HTTP sessions or other resources should override this method.
        """


class EmbeddingProviderError(Exception):
    """Raised when an embedding provider encounters an unrecoverable error."""
