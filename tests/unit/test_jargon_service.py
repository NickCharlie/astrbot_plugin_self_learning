from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from webui.services.jargon_service import JargonService


@pytest.mark.unit
def test_format_jargon_for_frontend_keeps_legacy_and_macos_fields():
    formatted = JargonService._format_jargon_for_frontend(
        {
            "id": 1,
            "content": "yyds",
            "meaning": "永远的神",
            "is_jargon": True,
            "is_global": False,
            "count": 3,
            "chat_id": "group-a",
            "raw_content": '["上下文"]',
            "last_inference_count": 3,
            "is_complete": True,
            "updated_at": 1234567890,
        }
    )

    assert formatted["term"] == "yyds"
    assert formatted["content"] == "yyds"
    assert formatted["is_confirmed"] is True
    assert formatted["is_jargon"] is True
    assert formatted["occurrences"] == 3
    assert formatted["count"] == 3
    assert formatted["group_id"] == "group-a"
    assert formatted["chat_id"] == "group-a"
    assert formatted["context_examples"] == ["上下文"]
    assert formatted["is_complete"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_jargon_groups_adds_legacy_count_aliases():
    database_manager = SimpleNamespace(
        get_jargon_groups=AsyncMock(
            return_value=[
                {
                    "group_id": "group-a",
                    "chat_id": "group-a",
                    "count": 2,
                }
            ]
        )
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    groups = await service.get_jargon_groups()

    assert groups == [
        {
            "group_id": "group-a",
            "group_name": "group-a",
            "id": "group-a",
            "chat_id": "group-a",
            "count": 2,
            "confirmed_jargon": 2,
            "total_candidates": 2,
        }
    ]
