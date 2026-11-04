"""Regression coverage for framework LLM provider lifecycle and role boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from astrbot.core.provider.entities import ProviderType

import core.framework_llm_adapter as adapter_module
from core.framework_llm_adapter import FrameworkLLMAdapter


def _chat_provider(provider_id: str, model: str):
    provider = Mock()
    provider.meta = Mock(
        return_value=SimpleNamespace(
            id=provider_id,
            model=model,
            provider_type=ProviderType.CHAT_COMPLETION,
        )
    )
    provider.text_chat = AsyncMock(
        return_value=SimpleNamespace(completion_text="ok")
    )
    return provider


ROLES = ("filter", "refine", "reinforce")


def _adapter(registry, **configured_roles):
    context = SimpleNamespace(
        get_all_providers=Mock(side_effect=lambda: list(registry.values())),
        get_provider_by_id=Mock(side_effect=registry.get),
    )
    config = SimpleNamespace(**{
        f"{role}_provider_id": configured_roles.get(role)
        for role in ROLES
    })
    adapter = FrameworkLLMAdapter(context)
    adapter.initialize_providers(config)
    return adapter


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_call_rebinds_provider_and_retries_once_on_stale_model_error(role):
    old_provider = _chat_provider("chat-a", "deleted-model")
    new_provider = _chat_provider("chat-a", "live-model")
    registry = {"chat-a": old_provider}

    async def replace_after_error(**kwargs):
        registry["chat-a"] = new_provider
        raise RuntimeError("404 model is not found")

    old_provider.text_chat.side_effect = replace_after_error
    adapter = _adapter(registry, **{role: "chat-a"})

    result = await getattr(adapter, f"{role}_chat_completion")("hello")

    assert result == "ok"
    assert getattr(adapter, f"{role}_provider") is new_provider
    assert adapter.call_stats[role]["errors"] == 0
    old_provider.text_chat.assert_awaited_once()
    new_provider.text_chat.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("invalid_type", [False, True])
@pytest.mark.parametrize("configure_other_role", [False, True])
async def test_explicit_missing_or_invalid_provider_never_falls_back(
    role, invalid_type, configure_other_role
):
    other_provider = _chat_provider("other", "other-model")
    registry = {"other": other_provider}
    unavailable = None
    if invalid_type:
        unavailable = _chat_provider("unavailable", "embedding-model")
        unavailable.meta.return_value.provider_type = ProviderType.EMBEDDING
        registry["unavailable"] = unavailable
    configured_roles = {role: "unavailable"}
    if configure_other_role:
        configured_roles[next(other for other in ROLES if other != role)] = "other"

    adapter = _adapter(registry, **configured_roles)

    assert getattr(adapter, f"{role}_provider") is None
    for _ in range(3):
        assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    other_provider.text_chat.assert_not_awaited()
    if unavailable:
        unavailable.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_deleted_provider_is_not_called_or_replaced_by_another_role(role):
    old_provider = _chat_provider("selected", "old-model")
    other_provider = _chat_provider("other", "other-model")
    registry = {"selected": old_provider, "other": other_provider}
    other_role = next(other for other in ROLES if other != role)
    adapter = _adapter(registry, **{role: "selected", other_role: "other"})

    # Populate the filter cache as well as exercising the selected provider.
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    del registry["selected"]
    for _ in range(3):
        assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    assert getattr(adapter, f"{role}_provider") is None
    old_provider.text_chat.assert_awaited_once()
    other_provider.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_same_id_replacement_uses_current_object_and_discards_old_cache(role):
    old_provider = _chat_provider("selected", "old-model")
    old_provider.text_chat.return_value.completion_text = "old"
    registry = {"selected": old_provider}
    adapter = _adapter(registry, **{role: "selected"})
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "old"

    new_provider = _chat_provider("selected", "new-model")
    new_provider.text_chat.return_value.completion_text = "new"
    registry["selected"] = new_provider
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "new"
    assert getattr(adapter, f"{role}_provider") is new_provider
    old_provider.text_chat.assert_awaited_once()
    new_provider.text_chat.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_same_id_replaced_with_non_chat_provider_stops_calls(role):
    old_provider = _chat_provider("selected", "old-model")
    registry = {"selected": old_provider}
    adapter = _adapter(registry, **{role: "selected"})
    invalid_provider = _chat_provider("selected", "embedding-model")
    invalid_provider.meta.return_value.provider_type = ProviderType.EMBEDDING
    registry["selected"] = invalid_provider

    assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    old_provider.text_chat.assert_not_awaited()
    invalid_provider.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_connection_error_does_not_add_adapter_retry_or_switch_provider(role):
    selected = _chat_provider("selected", "selected-model")
    selected.text_chat.side_effect = ConnectionError("Connection error.")
    other = _chat_provider("other", "other-model")
    registry = {"selected": selected, "other": other}
    adapter = _adapter(registry, **{role: "selected"})

    assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    selected.text_chat.assert_awaited_once()
    other.text_chat.assert_not_awaited()
    adapter.context.get_all_providers.assert_called_once()
    assert adapter.call_stats[role]["errors"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_provider_deleted_during_404_rebind_does_not_switch_supplier(role):
    selected = _chat_provider("selected", "selected-model")
    other = _chat_provider("other", "other-model")
    registry = {"selected": selected, "other": other}
    other_role = next(other_role for other_role in ROLES if other_role != role)

    async def remove_after_error(**kwargs):
        del registry["selected"]
        raise RuntimeError("404 model is not found")

    selected.text_chat.side_effect = remove_after_error
    adapter = _adapter(registry, **{role: "selected", other_role: "other"})

    assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    assert await getattr(adapter, f"{role}_chat_completion")("again") is None
    selected.text_chat.assert_awaited_once()
    other.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_empty_ids_preserve_automatic_provider_assignment():
    provider = _chat_provider("automatic", "automatic-model")
    adapter = _adapter({"automatic": provider})

    assert adapter.providers_configured == 3
    for role in ROLES:
        assert getattr(adapter, f"{role}_provider") is provider
        assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    assert provider.text_chat.await_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_unconfigured_role_preserves_fallback_to_an_explicit_other_role(role):
    provider = _chat_provider("other", "other-model")
    other_role = next(other for other in ROLES if other != role)
    adapter = _adapter({"other": provider}, **{other_role: "other"})

    assert getattr(adapter, f"{role}_provider") is None
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    provider.text_chat.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_explicit_missing_id_can_resume_when_same_id_is_registered(role):
    other = _chat_provider("other", "other-model")
    registry = {"other": other}
    adapter = _adapter(registry, **{role: "selected"})
    assert await getattr(adapter, f"{role}_chat_completion")("hello") is None

    selected = _chat_provider("selected", "selected-model")
    registry["selected"] = selected
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    selected.text_chat.assert_awaited_once()
    other.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_filter_inflight_and_cache_are_isolated_after_same_id_replacement():
    started = asyncio.Event()
    release = asyncio.Event()
    old = _chat_provider("selected", "old-model")
    new = _chat_provider("selected", "new-model")
    new.text_chat.return_value.completion_text = "new"

    async def blocked_old_call(**kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(completion_text="old")

    old.text_chat.side_effect = blocked_old_call
    registry = {"selected": old}
    adapter = _adapter(registry, filter="selected")
    old_task = asyncio.create_task(adapter.filter_chat_completion("same prompt"))
    try:
        await asyncio.wait_for(started.wait(), 1)
        registry["selected"] = new

        # The new request must complete before the old generation is released.
        assert await asyncio.wait_for(adapter.filter_chat_completion("same prompt"), 1) == "new"
        release.set()
        assert await old_task is None
        assert await adapter.filter_chat_completion("same prompt") == "new"
        old.text_chat.assert_awaited_once()
        new.text_chat.assert_awaited_once()
    finally:
        release.set()
        await asyncio.gather(old_task, return_exceptions=True)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_provider_deleted_while_inflight_discards_result_and_does_not_cache(role):
    started = asyncio.Event()
    release = asyncio.Event()
    selected = _chat_provider("selected", "selected-model")

    async def blocked_call(**kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(completion_text="outdated")

    selected.text_chat.side_effect = blocked_call
    registry = {"selected": selected}
    adapter = _adapter(registry, **{role: "selected"})
    call = getattr(adapter, f"{role}_chat_completion")
    task = asyncio.create_task(call("same prompt"))
    try:
        await asyncio.wait_for(started.wait(), 1)
        del registry["selected"]
        assert await call("same prompt") is None
        release.set()
        assert await task is None
        assert await call("same prompt") is None
        selected.text_chat.assert_awaited_once()
        assert adapter._filter_cache == {}
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_has_provider_recovers_same_id_after_temporary_registry_gap(role):
    old = _chat_provider("selected", "old-model")
    registry = {"selected": old}
    adapter = _adapter(registry, **{role: "selected"})
    has_provider = getattr(adapter, f"has_{role}_provider")
    del registry["selected"]
    assert has_provider() is False

    new = _chat_provider("selected", "new-model")
    registry["selected"] = new
    assert has_provider() is True
    assert adapter.providers_configured == 1
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    old.text_chat.assert_not_awaited()
    new.text_chat.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("explicit_id", [False, True])
async def test_has_provider_finishes_lazy_binding_when_registry_becomes_ready(role, explicit_id):
    registry = {}
    adapter = _adapter(registry, **({role: "selected"} if explicit_id else {}))
    assert adapter._needs_lazy_init is True

    provider = _chat_provider("selected", "selected-model")
    registry["selected"] = provider
    assert getattr(adapter, f"has_{role}_provider")() is True
    assert await getattr(adapter, f"{role}_chat_completion")("hello") == "ok"
    provider.text_chat.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ROLES)
async def test_repeated_missing_checks_warn_once_and_reset_after_recovery(role, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(adapter_module, "logger", logger)
    other = _chat_provider("other", "other-model")
    registry = {"other": other}
    adapter = _adapter(registry, **{role: "selected"})
    logger.reset_mock()
    has_provider = getattr(adapter, f"has_{role}_provider")
    for _ in range(3):
        assert has_provider() is False
        assert await getattr(adapter, f"{role}_chat_completion")("hello") is None
    assert logger.warning.call_count == 1

    registry["selected"] = _chat_provider("selected", "selected-model")
    assert has_provider() is True
    del registry["selected"]
    assert has_provider() is False
    assert logger.warning.call_count == 2
    other.text_chat.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_automatic_binding_recovers_after_all_roles_observe_registry_gap():
    old = _chat_provider("selected", "old-model")
    registry = {"selected": old}
    adapter = _adapter(registry)
    registry.clear()
    for role in ROLES:
        assert getattr(adapter, f"has_{role}_provider")() is False
    assert adapter._needs_lazy_init is True

    new = _chat_provider("selected", "new-model")
    registry["selected"] = new
    # Simulate expiration of the existing 30-second lazy-init cooldown.
    adapter._last_lazy_init_attempt = 0
    for role in ROLES:
        assert getattr(adapter, f"has_{role}_provider")() is True
        assert getattr(adapter, f"{role}_provider") is new
    assert adapter.providers_configured == 3
    assert await adapter.refine_chat_completion("hello") == "ok"
    old.text_chat.assert_not_awaited()
    new.text_chat.assert_awaited_once()
