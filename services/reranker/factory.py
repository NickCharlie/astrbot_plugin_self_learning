"""
Reranker provider factory.

Creates ``IRerankProvider`` instances by resolving AstrBot framework
providers via ``context.get_provider_by_id(provider_id)``.
"""

from typing import Optional

from astrbot.api import logger
from astrbot.core.provider.provider import RerankProvider as FrameworkRerankProvider

from ..provider_registry import (
    collect_framework_providers,
    find_provider_by_id,
    framework_registry_has_any_provider,
    normalize_provider_id,
)
from .base import IRerankProvider
from .framework_adapter import FrameworkRerankAdapter


class RerankProviderFactory:
    """Factory for creating reranker provider instances.

    Usage::

        reranker = RerankProviderFactory.create(config, context)
        if reranker:
            results = await reranker.rerank("query", ["doc1", "doc2"])
    """

    @staticmethod
    def create(config, context) -> Optional[IRerankProvider]:
        """Create a reranker provider from plugin configuration.

        Args:
            config: ``PluginConfig`` instance with ``rerank_provider_id``.
            context: AstrBot plugin context.

        Returns:
            An ``IRerankProvider`` instance, or ``None`` if not configured.
        """
        provider_id = normalize_provider_id(
            getattr(config, "rerank_provider_id", None)
        )

        if not provider_id:
            logger.debug(
                "[RerankFactory] No rerank_provider_id configured, "
                "reranking disabled"
            )
            return None

        if context is None:
            logger.warning(
                "[RerankFactory] AstrBot context is None, "
                "cannot resolve reranker provider"
            )
            return None

        providers, inspected, errors = collect_framework_providers(
            context,
            FrameworkRerankProvider,
            context_getter_name="get_all_rerank_providers",
            manager_list_name="rerank_provider_insts",
        )
        for error in errors:
            logger.debug(f"[RerankFactory] Registry inspection failed: {error}")

        if inspected:
            provider = find_provider_by_id(providers, provider_id)
            if provider is not None:
                return RerankProviderFactory._wrap_provider(
                    provider_id, provider
                )

            if not providers:
                registry_has_any_provider, _, any_errors = (
                    framework_registry_has_any_provider(context)
                )
                for error in any_errors:
                    logger.debug(
                        f"[RerankFactory] Provider readiness inspection failed: {error}"
                    )
                if not registry_has_any_provider:
                    logger.info(
                        "[RerankFactory] Framework provider registry is "
                        "not ready; reranker provider resolution will retry later"
                    )
                    return None

                logger.warning(
                    f"[RerankFactory] No rerank providers are visible "
                    f"in the framework registry; configured id='{provider_id}'"
                )
                return None

            available_ids = RerankProviderFactory._provider_ids(providers)
            logger.warning(
                f"[RerankFactory] Provider '{provider_id}' not found "
                f"in rerank registry; available={available_ids}"
            )
            return None

        try:
            provider = context.get_provider_by_id(provider_id)
        except Exception as exc:
            logger.warning(
                f"[RerankFactory] Failed to look up provider "
                f"'{provider_id}': {exc}"
            )
            return None

        if provider is None:
            logger.warning(
                f"[RerankFactory] Provider '{provider_id}' not found "
                f"in framework registry"
            )
            return None

        return RerankProviderFactory._wrap_provider(provider_id, provider)

    @staticmethod
    def _wrap_provider(
        provider_id: str,
        provider: FrameworkRerankProvider,
    ) -> Optional[IRerankProvider]:
        """Validate and wrap an already-resolved framework provider."""
        if not isinstance(provider, FrameworkRerankProvider):
            logger.warning(
                f"[RerankFactory] Provider '{provider_id}' is "
                f"{type(provider).__name__}, expected RerankProvider"
            )
            return None

        adapter = FrameworkRerankAdapter(provider)
        logger.info(
            f"[RerankFactory] Resolved reranker provider: "
            f"id={provider_id}, model={adapter.get_model_name()}"
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
