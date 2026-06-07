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

from ..provider_registry import (
    collect_framework_providers,
    find_provider_by_id,
    framework_registry_has_any_provider,
    normalize_provider_id,
)
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
        provider_id = normalize_provider_id(
            getattr(config, "embedding_provider_id", None)
        )

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
        providers, inspected, errors = collect_framework_providers(
            context,
            EmbeddingProvider,
            context_getter_name="get_all_embedding_providers",
            manager_list_name="embedding_provider_insts",
        )
        for error in errors:
            logger.debug(f"[EmbeddingFactory] Registry inspection failed: {error}")

        if inspected:
            provider = find_provider_by_id(providers, provider_id)
            if provider is not None:
                return EmbeddingProviderFactory._wrap_provider(
                    provider_id, provider
                )

            if not providers:
                registry_has_any_provider, _, any_errors = (
                    framework_registry_has_any_provider(context)
                )
                for error in any_errors:
                    logger.debug(
                        f"[EmbeddingFactory] Provider readiness inspection failed: {error}"
                    )
                if not registry_has_any_provider:
                    logger.info(
                        "[EmbeddingFactory] Framework provider registry is "
                        "not ready; embedding provider resolution will retry later"
                    )
                    return None

                logger.warning(
                    f"[EmbeddingFactory] No embedding providers are visible "
                    f"in the framework registry; configured id='{provider_id}'"
                )
                return None

            available_ids = EmbeddingProviderFactory._provider_ids(providers)
            logger.warning(
                f"[EmbeddingFactory] Provider '{provider_id}' not found "
                f"in embedding registry; available={available_ids}"
            )
            return None

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

        return EmbeddingProviderFactory._wrap_provider(provider_id, provider)

    @staticmethod
    def _wrap_provider(
        provider_id: str,
        provider: EmbeddingProvider,
    ) -> Optional[IEmbeddingProvider]:
        """Validate and wrap an already-resolved framework provider."""
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

    @staticmethod
    def _provider_ids(providers) -> list[str]:
        """Return visible provider IDs for diagnostics."""
        ids: list[str] = []
        for provider in providers:
            try:
                ids.append(provider.meta().id)
            except Exception:
                continue
        return ids
