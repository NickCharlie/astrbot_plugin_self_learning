import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.config import PluginConfig
from self_learning_EterU.core.feature_delegation import FeatureDelegation
from self_learning_EterU.core.factory import ServiceFactory
from self_learning_EterU.services.hooks.llm_hook_handler import LLMHookHandler


def _star(name, *, root_dir_name=None, active=True, loaded=True):
    return SimpleNamespace(
        name=name,
        display_name=None,
        root_dir_name=root_dir_name,
        module_path=f"data.plugins.{root_dir_name or name}.main",
        activated=active,
        star_cls=object() if loaded else None,
    )


def _context(*stars):
    return SimpleNamespace(
        get_all_stars=lambda: list(stars),
        get_registered_star=lambda name: next(
            (star for star in stars if str(star.name).lower() == str(name).lower()),
            None,
        ),
    )


def test_feature_delegation_detects_loaded_companion_plugins():
    config = PluginConfig()
    delegation = FeatureDelegation(
        config,
        _context(
            _star("LivingMemory", root_dir_name="astrbot_plugin_livingmemory"),
            _star("astrbot_plugin_group_chat_plus"),
        ),
    )

    assert delegation.should_delegate_memory() is True
    assert delegation.should_delegate_reply() is True
    assert delegation.status()["memory_plugin"] == "LivingMemory"
    assert delegation.status()["reply_plugin"] == "astrbot_plugin_group_chat_plus"


def test_feature_delegation_uses_registered_star_without_full_scan():
    config = PluginConfig()
    livingmemory = _star("LivingMemory", root_dir_name="astrbot_plugin_livingmemory")
    context = SimpleNamespace(
        get_registered_star=lambda name: livingmemory if name == "LivingMemory" else None
    )

    delegation = FeatureDelegation(config, context)

    assert delegation.should_delegate_memory() is True


def test_feature_delegation_keeps_local_fallback_when_companion_missing_or_disabled():
    config = PluginConfig(delegate_memory_to_livingmemory=False)
    delegation = FeatureDelegation(
        config,
        _context(_star("LivingMemory", root_dir_name="astrbot_plugin_livingmemory")),
    )

    assert delegation.should_delegate_memory() is False

    config = PluginConfig()
    delegation = FeatureDelegation(
        config,
        _context(_star("LivingMemory", active=False)),
    )

    assert delegation.should_delegate_memory() is False


@pytest.mark.asyncio
async def test_llm_hook_omits_local_v2_memories_when_livingmemory_delegated():
    v2 = SimpleNamespace(
        get_enhanced_context=AsyncMock(
            return_value={
                "knowledge_context": "knowledge stays local",
                "related_memories": ["local memory should not be injected"],
                "few_shot_examples": ["style example"],
            }
        )
    )
    delegation = SimpleNamespace(should_delegate_memory=lambda: True)
    handler = LLMHookHandler(
        plugin_config=SimpleNamespace(rerank_top_k=5),
        diversity_manager=object(),
        social_context_injector=None,
        v2_integration=v2,
        jargon_query_service=None,
        temporary_persona_updater=None,
        perf_tracker=SimpleNamespace(record=lambda payload: None),
        group_id_to_unified_origin={},
        db_manager=None,
        feature_delegation=delegation,
    )

    result = await handler._fetch_v2("query", "group-a")

    assert result == {
        "knowledge_context": "knowledge stays local",
        "few_shot_examples": ["style example"],
    }


@pytest.mark.asyncio
async def test_service_factory_initialize_all_services_can_skip_local_responder():
    factory = ServiceFactory.__new__(ServiceFactory)
    factory.config = SimpleNamespace(debug_mode=False)
    factory._logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    factory._registry = SimpleNamespace(start_all_services=AsyncMock(return_value=True))
    calls = []

    for name in (
        "create_database_manager",
        "create_temporary_persona_updater",
        "create_message_collector",
        "create_style_analyzer",
        "create_quality_monitor",
        "create_ml_analyzer",
        "create_response_diversity_manager",
        "create_intelligent_responder",
        "create_persona_manager",
        "create_multidimensional_analyzer",
        "create_progressive_learning",
    ):
        setattr(factory, name, lambda name=name: calls.append(name))

    success = await factory.initialize_all_services(skip_intelligent_responder=True)

    assert success is True
    assert "create_intelligent_responder" not in calls
