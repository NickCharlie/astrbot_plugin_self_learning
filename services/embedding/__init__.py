"""
Embedding provider abstraction layer.

Provides a plugin-level ``IEmbeddingProvider`` interface that delegates to
AstrBot framework's ``EmbeddingProvider`` via a thin adapter.  The factory
resolves providers by their framework-configured ``provider_id``.

Public API::

    from services.embedding import (
        IEmbeddingProvider,
        EmbeddingResult,
        EmbeddingProviderError,
        EmbeddingProviderFactory,
        FrameworkEmbeddingAdapter,
    )
"""

from .base import EmbeddingProviderError, EmbeddingResult, IEmbeddingProvider
from .factory import EmbeddingProviderFactory
from .framework_adapter import FrameworkEmbeddingAdapter

__all__ = [
    "IEmbeddingProvider",
    "EmbeddingResult",
    "EmbeddingProviderError",
    "EmbeddingProviderFactory",
    "FrameworkEmbeddingAdapter",
]
