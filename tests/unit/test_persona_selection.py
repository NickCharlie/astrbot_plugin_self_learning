from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utils.persona_selection import (
    _RECENT_WARNINGS,
    get_configured_persona_id,
    get_persona_identifier,
    resolve_target_persona,
)


@pytest.mark.asyncio
async def test_resolve_target_persona_prefers_plugin_configured_persona():
    manager = AsyncMock()
    manager.get_persona.return_value = {
        "persona_id": "suleng",
        "name": "Suleng Persona",
        "system_prompt": "Configured prompt",
        "begin_dialogs": ["hi", "hello"],
    }
    manager.get_default_persona_v3.return_value = {
        "persona_id": "default",
        "name": "default",
        "prompt": "Default prompt",
    }
    config = SimpleNamespace(current_persona_name="suleng")

    persona = await resolve_target_persona(manager, config, "aiocqhttp:group:1", require_existing=True)

    assert persona["persona_id"] == "suleng"
    assert persona["prompt"] == "Configured prompt"
    manager.get_persona.assert_awaited_once_with("suleng")
    manager.get_default_persona_v3.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_target_persona_falls_back_to_single_existing_when_default_missing():
    manager = AsyncMock()
    manager.get_persona.side_effect = ValueError("Persona with ID default does not exist.")
    manager.get_default_persona_v3.return_value = {
        "persona_id": "default",
        "name": "default",
        "prompt": "Default prompt",
    }
    manager.get_all_personas.return_value = [
        {
            "persona_id": "suleng",
            "name": "Suleng Persona",
            "system_prompt": "Only prompt",
            "begin_dialogs": [],
        }
    ]
    config = SimpleNamespace(current_persona_name="default")

    persona = await resolve_target_persona(manager, config, "aiocqhttp:group:1", require_existing=True)

    assert persona["persona_id"] == "suleng"
    assert persona["selection_source"] == "single_existing"
    manager.get_persona.assert_not_awaited()


def test_default_persona_config_means_follow_astrbot_current_persona():
    assert get_configured_persona_id(SimpleNamespace(current_persona_name="default")) is None
    assert get_configured_persona_id(SimpleNamespace(current_persona_name="")) is None


@pytest.mark.asyncio
async def test_missing_current_persona_warning_is_throttled():
    _RECENT_WARNINGS.clear()
    manager = AsyncMock()
    manager.get_default_persona_v3.return_value = {
        "persona_id": "default",
        "name": "default",
        "prompt": "Default prompt",
    }
    manager.get_persona.return_value = None
    manager.get_all_personas.return_value = []
    log = SimpleNamespace(warning=Mock())

    config = SimpleNamespace(current_persona_name="")

    await resolve_target_persona(manager, config, "aiocqhttp:group:1", require_existing=True, log=log)
    await resolve_target_persona(manager, config, "aiocqhttp:group:1", require_existing=True, log=log)

    assert log.warning.call_count == 1


def test_get_persona_identifier_uses_persona_id_before_display_name():
    persona = {
        "persona_id": "suleng",
        "name": "Suleng Persona",
        "system_prompt": "Configured prompt",
    }

    assert get_persona_identifier(persona) == "suleng"
