"""
Reranker provider factory.

Creates ``IRerankProvider`` instances by resolving AstrBot framework
providers via ``context.get_provider_by_id(provider_id)``.
"""

from typing import Optional

from astrbot.api import logger
from astrbot.core.provider.provider import RerankProvider as FrameworkRerankProvider

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
        provider_id = getattr(config, "rerank_provider_id", None)

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
