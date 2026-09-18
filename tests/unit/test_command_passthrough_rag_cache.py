"""Issue #254 / #253 回归测试：命令直接放行与 LightRAG LLM 响应缓存治理"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from self_learning_EterU.services.commands.command_filter import CommandFilter
from self_learning_EterU.services.commands.handlers import PluginCommandHandlers
from self_learning_EterU.services.hooks.llm_hook_handler import LLMHookHandler
from self_learning_EterU.services.integration import lightrag_knowledge_manager as lkm


# ---------------------------------------------------------------------------
# Issue #254: 命令/系统级唤醒词直接放行
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/learning_status", True),
        ("#remember 这段要记住", True),
        ("!provider", True),
        (".help", True),
        ("今天天气怎么样", False),
        ("/123", False),
        ("//_comment", False),
        ("", False),
        (None, False),
    ],
)
def test_command_filter_detects_command_text(text, expected):
    assert CommandFilter.is_command_text(text) is expected


def _make_event(message_text):
    return SimpleNamespace(
        message_str=message_text,
        get_message_str=lambda: message_text,
        get_group_id=lambda: "group-1",
        get_sender_id=lambda: "user-1",
        unified_msg_origin="qq:group:group-1",
    )


def _make_handler(config, diversity_manager):
    return LLMHookHandler(
        plugin_config=config,
        diversity_manager=diversity_manager,
        social_context_injector=None,
        v2_integration=None,
        jargon_query_service=None,
        temporary_persona_updater=None,
        perf_tracker=SimpleNamespace(record=lambda payload: None),
        group_id_to_unified_origin={},
    )


def _hook_config(**overrides):
    values = {
        "enable_llm_hooks": True,
        "enable_command_pass_through": True,
        "llm_hook_context_timeout": 0.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_llm_hook_skips_injection_for_command_messages():
    diversity_manager = AsyncMock()
    handler = _make_handler(_hook_config(), diversity_manager)
    req = SimpleNamespace(prompt="帮我记住一段话", extra_user_content_parts=None)

    await handler.handle(_make_event("/remember 记住这段"), req)

    diversity_manager.build_diversity_prompt_injection.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_hook_still_injects_for_normal_messages():
    diversity_manager = AsyncMock()
    diversity_manager.build_diversity_prompt_injection.return_value = "风格注入"
    diversity_manager.get_current_style.return_value = "default"
    diversity_manager.get_current_pattern.return_value = "chat"
    handler = _make_handler(_hook_config(), diversity_manager)
    req = SimpleNamespace(prompt="今天天气怎么样", extra_user_content_parts=None)

    await handler.handle(_make_event("今天天气怎么样"), req)

    diversity_manager.build_diversity_prompt_injection.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_hook_pass_through_can_be_disabled():
    diversity_manager = AsyncMock()
    diversity_manager.build_diversity_prompt_injection.return_value = None
    handler = _make_handler(
        _hook_config(enable_command_pass_through=False), diversity_manager
    )
    req = SimpleNamespace(prompt="/provider", extra_user_content_parts=None)

    await handler.handle(_make_event("/provider 查看列表"), req)

    diversity_manager.build_diversity_prompt_injection.assert_awaited_once()


# ---------------------------------------------------------------------------
# Issue #253: LightRAG llm_response_cache 治理
# ---------------------------------------------------------------------------


@pytest.fixture
def rag_env(tmp_path, monkeypatch):
    """Construct a manager without the optional lightrag dependency."""
    monkeypatch.setattr(lkm, "_LIGHTRAG_AVAILABLE", True)
    config = SimpleNamespace(
        data_dir=str(tmp_path),
        lightrag_enable_llm_cache=False,
    )
    manager = lkm.LightRAGKnowledgeManager(
        config, llm_adapter=object(), embedding_provider=None
    )
    return manager, tmp_path


def _write_cache_file(base_dir, group_id, content=b"x" * 2048):
    group_dir = base_dir / "lightrag" / group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    cache_file = group_dir / lkm.LLM_RESPONSE_CACHE_FILENAME
    cache_file.write_bytes(content)
    return cache_file


@pytest.mark.asyncio
async def test_start_sweeps_stale_cache_files_when_disabled(rag_env):
    manager, tmp_path = rag_env
    cache_file = _write_cache_file(tmp_path, "12345")

    await manager.start()

    assert not cache_file.exists()


@pytest.mark.asyncio
async def test_start_keeps_cache_files_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(lkm, "_LIGHTRAG_AVAILABLE", True)
    config = SimpleNamespace(
        data_dir=str(tmp_path),
        lightrag_enable_llm_cache=True,
    )
    manager = lkm.LightRAGKnowledgeManager(
        config, llm_adapter=object(), embedding_provider=None
    )
    cache_file = _write_cache_file(tmp_path, "12345")

    await manager.start()

    assert cache_file.exists()


@pytest.mark.asyncio
async def test_clear_llm_response_cache_removes_cold_files(rag_env):
    manager, tmp_path = rag_env
    cache_a = _write_cache_file(tmp_path, "111")
    cache_b = _write_cache_file(tmp_path, "222")
    expected_bytes = cache_a.stat().st_size + cache_b.stat().st_size

    result = await manager.clear_llm_response_cache()

    assert sorted(result["cleared"]) == ["111", "222"]
    assert result["freed_bytes"] >= expected_bytes
    assert not cache_a.exists() and not cache_b.exists()


@pytest.mark.asyncio
async def test_clear_llm_response_cache_group_filter(rag_env):
    manager, tmp_path = rag_env
    cache_a = _write_cache_file(tmp_path, "111")
    cache_b = _write_cache_file(tmp_path, "222")

    result = await manager.clear_llm_response_cache(group_ids=["111"])

    assert result["cleared"] == ["111"]
    assert not cache_a.exists() or cache_a.stat().st_size == 0
    assert cache_b.exists()


@pytest.mark.asyncio
async def test_clear_llm_response_cache_uses_api_for_warm_instances(
    rag_env, monkeypatch
):
    manager, tmp_path = rag_env
    cache_file = _write_cache_file(tmp_path, "111")
    warm_rag = SimpleNamespace(aclear_cache=AsyncMock())
    manager._instances["111"] = warm_rag

    result = await manager.clear_llm_response_cache(group_ids=["111"])

    warm_rag.aclear_cache.assert_awaited_once()
    assert result["cleared"] == ["111"]
    assert result["errors"] == []
    assert cache_file.exists()  # 模拟实例不落盘，文件保持原样


@pytest.mark.asyncio
async def test_get_rag_disables_llm_cache_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(lkm, "_LIGHTRAG_AVAILABLE", True)
    captured_kwargs = {}

    class _DummyRAG:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        async def initialize_storages(self):
            return None

        async def initialize_pipeline_status(self):
            return None

    monkeypatch.setattr(lkm, "LightRAG", _DummyRAG)
    monkeypatch.setattr(
        lkm, "EmbeddingFunc", lambda **kwargs: SimpleNamespace(**kwargs)
    )
    embedding = SimpleNamespace(get_dim=lambda: 1024, get_embeddings=AsyncMock())
    config = SimpleNamespace(
        data_dir=str(tmp_path),
        lightrag_enable_llm_cache=False,
    )
    manager = lkm.LightRAGKnowledgeManager(
        config, llm_adapter=object(), embedding_provider=embedding
    )

    stale = _write_cache_file(tmp_path, "12345")
    await manager._get_rag("12345")

    assert captured_kwargs["enable_llm_cache"] is False
    assert captured_kwargs["enable_llm_cache_for_entity_extract"] is False
    assert not stale.exists()


# ---------------------------------------------------------------------------
# /clean_rag_cache 命令
# ---------------------------------------------------------------------------


def _make_command_handler(v2_integration):
    return PluginCommandHandlers(
        plugin_config=SimpleNamespace(),
        service_factory=None,
        message_collector=None,
        persona_manager=None,
        progressive_learning=None,
        affection_manager=None,
        temporary_persona_updater=None,
        db_manager=None,
        llm_adapter=None,
        v2_integration=v2_integration,
    )


def _command_event(message_text):
    return SimpleNamespace(
        get_message_str=lambda: message_text,
        plain_result=lambda text: text,
    )


async def _collect(async_gen):
    return [item async for item in async_gen]


@pytest.mark.asyncio
async def test_clean_rag_cache_parses_group_argument():
    clear_mock = AsyncMock(
        return_value={"cleared": ["111"], "freed_bytes": 1024, "errors": []}
    )
    handler = _make_command_handler(
        SimpleNamespace(
            _knowledge_manager=SimpleNamespace(
                clear_llm_response_cache=clear_mock
            )
        )
    )

    replies = await _collect(
        handler.clean_rag_cache(_command_event("/clean_rag_cache 111"))
    )

    clear_mock.assert_awaited_once_with(group_ids=["111"])
    assert any("清理完成" in reply for reply in replies)


@pytest.mark.asyncio
async def test_clean_rag_cache_without_argument_clears_all_groups():
    clear_mock = AsyncMock(
        return_value={"cleared": ["111", "222"], "freed_bytes": 2048, "errors": []}
    )
    handler = _make_command_handler(
        SimpleNamespace(
            _knowledge_manager=SimpleNamespace(
                clear_llm_response_cache=clear_mock
            )
        )
    )

    replies = await _collect(
        handler.clean_rag_cache(_command_event("/clean_rag_cache"))
    )

    clear_mock.assert_awaited_once_with(group_ids=None)
    assert any("111" in reply and "222" in reply for reply in replies)


@pytest.mark.asyncio
async def test_clean_rag_cache_reports_non_lightrag_engine():
    handler = _make_command_handler(
        SimpleNamespace(_knowledge_manager=None)
    )

    replies = await _collect(
        handler.clean_rag_cache(_command_event("/clean_rag_cache"))
    )

    assert any("不是 lightrag" in reply for reply in replies)
