"""
Reranker provider abstraction layer.

Provides a plugin-level ``IRerankProvider`` interface that delegates to
AstrBot framework's ``RerankProvider`` via a thin adapter.

Public API::

    from services.reranker import (
        IRerankProvider,
        RerankResult,
        RerankProviderError,
        RerankProviderFactory,
        FrameworkRerankAdapter,
    )
"""

from .base import IRerankProvider, RerankProviderError, RerankResult
from .factory import RerankProviderFactory
from .framework_adapter import FrameworkRerankAdapter

__all__ = [
    "IRerankProvider",
    "RerankResult",
    "RerankProviderError",
    "RerankProviderFactory",
    "FrameworkRerankAdapter",
]
