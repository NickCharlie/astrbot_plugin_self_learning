"""Regression coverage for AstrBot provider registry cold-start handling."""

import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    RerankProvider as FrameworkRerankProvider,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _load_plugin_package(alias: str):
    spec = importlib.util.spec_from_file_location(
        alias,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _cleanup_alias(alias: str) -> None:
    for name in list(sys.modules):
        if name == alias or name.startswith(f"{alias}."):
            sys.modules.pop(name, None)


@pytest.fixture
def plugin_modules():
    alias = "data.plugins.astrbot_plugin_self_learning_provider_rebind_test"
    _cleanup_alias(alias)
    _load_plugin_package(alias)
    try:
        yield SimpleNamespace(
            PluginConfig=importlib.import_module(f"{alias}.config").PluginConfig,
            V2LearningIntegration=importlib.import_module(
                f"{alias}.services.core_learning.v2_learning_integration"
            ).V2LearningIntegration,
            EmbeddingProviderFactory=importlib.import_module(
                f"{alias}.services.embedding.factory"
            ).EmbeddingProviderFactory,
            RerankProviderFactory=importlib.import_module(
                f"{alias}.services.reranker.factory"
            ).RerankProviderFactory,
        )
    finally:
        _cleanup_alias(alias)


class DummyEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_id: str = "embed-a") -> None:
        super().__init__({"id": provider_id, "type": "dummy_embedding"}, {})
        self._id = provider_id
        self.set_model("dummy-embedding")

    def meta(self):
        return SimpleNamespace(id=self._id)

    async def get_embedding(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[1.0, 2.0, 3.0] for _ in text]

    def get_dim(self) -> int:
        return 3


class DummyRerankProvider(FrameworkRerankProvider):
    def __init__(self, provider_id: str = "rerank-a") -> None:
        super().__init__({"id": provider_id, "type": "dummy_rerank"}, {})
        self._id = provider_id
        self.set_model("dummy-rerank")

    def meta(self):
        return SimpleNamespace(id=self._id)

    async def rerank(self, query: str, documents: list[str], top_n=None):
        return []


def test_embedding_factory_waits_when_framework_registry_is_empty(plugin_modules):
    config = SimpleNamespace(embedding_provider_id="embedding")
    context = SimpleNamespace(
        get_all_providers=Mock(return_value=[]),
        get_all_embedding_providers=Mock(return_value=[]),
        get_provider_by_id=Mock(side_effect=AssertionError("should not query by id")),
    )

    provider = plugin_modules.EmbeddingProviderFactory.create(config, context)

    assert provider is None
    context.get_provider_by_id.assert_not_called()


def test_rerank_factory_waits_when_framework_registry_is_empty(plugin_modules):
    config = SimpleNamespace(rerank_provider_id="rerank")
    context = SimpleNamespace(
        get_all_providers=Mock(return_value=[]),
        get_all_rerank_providers=Mock(return_value=[]),
        get_provider_by_id=Mock(side_effect=AssertionError("should not query by id")),
    )

    provider = plugin_modules.RerankProviderFactory.create(config, context)

    assert provider is None
    context.get_provider_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_v2_integration_rebinds_providers_after_registry_becomes_ready(plugin_modules):
    class MinimalV2LearningIntegration(plugin_modules.V2LearningIntegration):
        """Keep provider rebinding tests focused on provider wiring only."""

        def _create_social_analyzer(self):
            return None

        def _create_jargon_filter(self):
            return None

    embedding_providers = []
    rerank_providers = []
    context = SimpleNamespace(
        get_all_providers=Mock(return_value=[]),
        get_all_embedding_providers=Mock(side_effect=lambda: list(embedding_providers)),
        get_all_rerank_providers=Mock(side_effect=lambda: list(rerank_providers)),
        get_provider_by_id=Mock(side_effect=AssertionError("should not query by id")),
    )
    config = plugin_modules.PluginConfig(
        embedding_provider_id="embed-a",
        rerank_provider_id="rerank-a",
        knowledge_engine="legacy",
        memory_engine="legacy",
    )
    integration = MinimalV2LearningIntegration(
        config=config,
        llm_adapter=None,
        db_manager=None,
        context=context,
    )

    assert integration._embedding_provider is None
    assert integration._rerank_provider is None

    embedding_providers.append(DummyEmbeddingProvider("embed-a"))
    rerank_providers.append(DummyRerankProvider("rerank-a"))

    refreshed = await integration.refresh_provider_bindings(force=True)

    assert refreshed is True
    assert integration._embedding_provider.provider_id == "embed-a"
    assert integration._rerank_provider.provider_id == "rerank-a"
    context.get_provider_by_id.assert_not_called()
