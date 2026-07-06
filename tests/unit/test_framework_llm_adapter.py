"""Regression coverage for framework LLM provider rebinding."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from astrbot.core.provider.entities import ProviderType

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
    return provider


@pytest.mark.unit
@pytest.mark.asyncio
async def test_filter_call_rebinds_provider_and_retries_once_on_stale_model_error():
    old_provider = _chat_provider("chat-a", "deleted-model")
    old_provider.text_chat = AsyncMock(
        side_effect=RuntimeError("404 model is not found")
    )
    new_provider = _chat_provider("chat-a", "live-model")
    new_provider.text_chat = AsyncMock(
        return_value=SimpleNamespace(completion_text="ok")
    )

    context = SimpleNamespace(
        get_all_providers=Mock(side_effect=[[old_provider], [new_provider]]),
        get_provider_by_id=Mock(side_effect=[old_provider, new_provider]),
    )
    config = SimpleNamespace(
        filter_provider_id="chat-a",
        refine_provider_id=None,
        reinforce_provider_id=None,
    )

    adapter = FrameworkLLMAdapter(context)
    adapter.initialize_providers(config)

    result = await adapter.filter_chat_completion("hello")

    assert result == "ok"
    assert adapter.filter_provider is new_provider
    assert adapter.call_stats["filter"]["errors"] == 0
    old_provider.text_chat.assert_awaited_once()
    new_provider.text_chat.assert_awaited_once()
