from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.persona_selection import get_persona_identifier, resolve_target_persona


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


def test_get_persona_identifier_uses_persona_id_before_display_name():
    persona = {
        "persona_id": "suleng",
        "name": "Suleng Persona",
        "system_prompt": "Configured prompt",
    }

    assert get_persona_identifier(persona) == "suleng"
