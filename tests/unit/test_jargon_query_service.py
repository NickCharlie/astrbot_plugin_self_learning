from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.jargon.jargon_query import JargonQueryService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_jargon_uses_only_confirmed_group_and_global_terms():
    db = SimpleNamespace(
        search_jargon=AsyncMock(
            side_effect=[
                [
                    {
                        "id": 1,
                        "content": "上强度",
                        "meaning": "加大力度",
                    }
                ],
                [
                    {
                        "id": 2,
                        "content": "拉满",
                        "meaning": "做到极致",
                    }
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service.query_jargon("强度", chat_id="group-a", limit=3)

    assert "上强度" in result
    assert "拉满" in result
    assert db.search_jargon.await_args_list[0].kwargs == {
        "keyword": "强度",
        "chat_id": "group-a",
        "confirmed_only": True,
        "limit": 3,
    }
    assert db.search_jargon.await_args_list[1].kwargs == {
        "keyword": "强度",
        "chat_id": None,
        "confirmed_only": True,
        "global_only": True,
        "limit": 2,
    }
