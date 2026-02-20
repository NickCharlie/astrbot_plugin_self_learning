"""
Embedding provider factory.

Creates the appropriate ``IEmbeddingProvider`` implementation by looking up
the AstrBot framework's provider registry using a configured ``provider_id``.

This follows the same pattern as the plugin's ``FrameworkLLMAdapter``:
``context.get_provider_by_id(provider_id)`` → framework provider instance →
wrapped in a thin adapter.
"""

from typing import Optional

from astrbot.api import logger
from astrbot.core.provider.provider import EmbeddingProvider

from .base import IEmbeddingProvider
from .framework_adapter import FrameworkEmbeddingAdapter


class EmbeddingProviderFactory:
    """Factory for creating embedding provider instances.

    Usage::

        provider = EmbeddingProviderFactory.create(config, context)
        if provider:
            vec = await provider.get_embedding("hello")
    """

    @staticmethod
    def create(config, context) -> Optional[IEmbeddingProvider]:
        """Create an embedding provider from plugin configuration.

        Args:
            config: ``PluginConfig`` instance.  Expected field:
                - ``embedding_provider_id``: AstrBot provider ID string.
            context: AstrBot plugin context (provides ``get_provider_by_id``).

        Returns:
            An ``IEmbeddingProvider`` instance, or ``None`` if embedding is
            not configured.
        """
        provider_id = getattr(config, "embedding_provider_id", None)

        if not provider_id:
            logger.debug(
                "[EmbeddingFactory] No embedding_provider_id configured, "
                "embedding features disabled"
            )
            return None

        if context is None:
            logger.warning(
                "[EmbeddingFactory] AstrBot context is None, "
                "cannot resolve embedding provider"
            )
            return None

        return EmbeddingProviderFactory._resolve_framework_provider(
            provider_id, context
        )

    @staticmethod
    def _resolve_framework_provider(
        provider_id: str, context
    ) -> Optional[IEmbeddingProvider]:
        """Resolve the framework provider by ID and wrap in adapter."""
        try:
            provider = context.get_provider_by_id(provider_id)
        except Exception as exc:
            logger.warning(
                f"[EmbeddingFactory] Failed to look up provider "
                f"'{provider_id}': {exc}"
            )
            return None

        if provider is None:
            logger.warning(
                f"[EmbeddingFactory] Provider '{provider_id}' not found "
                f"in framework registry"
            )
            return None

        if not isinstance(provider, EmbeddingProvider):
            logger.warning(
                f"[EmbeddingFactory] Provider '{provider_id}' is "
                f"{type(provider).__name__}, expected EmbeddingProvider"
            )
            return None

        adapter = FrameworkEmbeddingAdapter(provider)
        logger.info(
            f"[EmbeddingFactory] Resolved embedding provider: "
            f"id={provider_id}, model={adapter.get_model_name()}, "
            f"dim={adapter.get_dim()}"
        )
        return adapter
