import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.response.intelligent_responder import (
    IntelligentResponder,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_responder_does_not_inline_related_memories():
    responder = IntelligentResponder(
        config=SimpleNamespace(),
        context=SimpleNamespace(),
        db_manager=SimpleNamespace(),
    )

    text = await responder._build_context_enhancement(
        {
            "sender_id": "user-a",
            "related_memories": ["raw long-term memory must stay dynamic"],
            "user_affection": {
                "affection_level": 10,
                "interaction_count": 1,
                "last_interaction": 0,
            },
            "group_atmosphere": {
                "activity_level": "low",
                "avg_message_length": 4,
                "total_recent_messages": 1,
            },
            "recent_messages": [],
        }
    )

    assert "raw long-term memory must stay dynamic" not in text
    assert "【用户信息】" in text

