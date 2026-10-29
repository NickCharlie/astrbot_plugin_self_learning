"""RememberService ↔ LivingMemory 2.8.x delegation tests."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.learning.remember_service import (  # noqa: E402
    RememberService,
)

class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        return None


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_args):
        return False


class _FakeDb:
    def __init__(self):
        self.session = _FakeSession()
        self.saved_memories = []
        self.reviews = []

    def get_session(self):
        return _FakeSessionContext(self.session)

    async def save_manual_memory(self, **kwargs):
        self.saved_memories.append(kwargs)
        return 7

    async def create_style_learning_review(self, data):
        self.reviews.append(data)
        return 3


def _delegation_with_engine(memory_engine):
    star = SimpleNamespace(
        star_cls=SimpleNamespace(
            initializer=SimpleNamespace(memory_engine=memory_engine)
        )
    )
    return SimpleNamespace(
        should_delegate_memory=lambda: True,
        memory_plugin=lambda: star,
    )


def _delegation_with_settings(memory_engine, settings):
    plugin = SimpleNamespace(
        initializer=SimpleNamespace(memory_engine=memory_engine),
        config_manager=SimpleNamespace(
            get=lambda key, default=None: settings.get(key, default)
        ),
    )
    star = SimpleNamespace(star_cls=plugin)
    return SimpleNamespace(
        should_delegate_memory=lambda: True,
        memory_plugin=lambda: star,
    )


@pytest.mark.asyncio
async def test_remember_delegates_to_livingmemory_engine():
    db = _FakeDb()
    add_memory = AsyncMock(return_value=42)
    service = RememberService(
        db,
        feature_delegation=_delegation_with_engine(
            SimpleNamespace(add_memory=add_memory)
        ),
        group_id_to_unified_origin={"group-a": "aiocqhttp:GroupMessage:group-a"},
    )

    result = await service.remember(
        group_id="group-a",
        sender_id="user-a",
        content="今天状态怎么样 => 我今天状态不错",
    )

    add_memory.assert_awaited_once()
    kwargs = add_memory.await_args.kwargs
    assert kwargs["session_id"] == "aiocqhttp:GroupMessage:group-a"
    assert kwargs["persona_id"] == "default"
    assert kwargs["metadata"]["source"] == "self_learning_remember"
    assert result.memory_id == 42
    assert db.saved_memories == []


@pytest.mark.asyncio
async def test_remember_falls_back_to_local_when_not_delegated():
    db = _FakeDb()
    add_memory = AsyncMock(return_value=42)
    service = RememberService(
        db,
        feature_delegation=SimpleNamespace(
            should_delegate_memory=lambda: False,
            memory_plugin=lambda: None,
        ),
    )

    result = await service.remember(
        group_id="group-a",
        sender_id="user-a",
        content="今天状态怎么样 => 我今天状态不错",
    )

    add_memory.assert_not_awaited()
    assert result.memory_id == 7
    assert db.saved_memories[0]["memory_type"] == "manual_remember"


@pytest.mark.asyncio
async def test_remember_falls_back_when_livingmemory_write_fails():
    db = _FakeDb()
    add_memory = AsyncMock(side_effect=RuntimeError("engine not ready"))
    service = RememberService(
        db,
        feature_delegation=_delegation_with_engine(
            SimpleNamespace(add_memory=add_memory)
        ),
    )

    result = await service.remember(
        group_id="group-a",
        sender_id="user-a",
        content="今天状态怎么样 => 我今天状态不错",
    )

    assert result.memory_id == 7
    assert len(db.saved_memories) == 1


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, "aiocqhttp:GroupMessage:group-a"),
        ({"filtering_settings.memory_scope_mode": "session"}, "aiocqhttp:GroupMessage:group-a"),
        ({"filtering_settings.memory_scope_mode": "global"}, "livingmemory:global"),
        (
            {"filtering_settings.memory_scope_mode": "user"},
            "livingmemory:user:aiocqhttp:user-a",
        ),
        ({"filtering_settings.use_session_filtering": False}, None),
        (
            {
                "filtering_settings.memory_scope_mode": "global",
                "filtering_settings.isolated_sessions": "aiocqhttp:GroupMessage:group-a",
            },
            "aiocqhttp:GroupMessage:group-a",
        ),
    ],
)
def test_livingmemory_scope_resolution(settings, expected):
    config_manager = SimpleNamespace(
        get=lambda key, default=None: settings.get(key, default)
    )
    service = RememberService(SimpleNamespace())

    resolved = service._resolve_livingmemory_session_id(
        plugin=SimpleNamespace(config_manager=config_manager),
        group_id="group-a",
        unified_origin="aiocqhttp:GroupMessage:group-a",
        sender_id="user-a",
    )

    assert resolved == expected


@pytest.mark.asyncio
async def test_remember_respects_livingmemory_whitelist_denial():
    db = _FakeDb()
    add_memory = AsyncMock(return_value=42)
    service = RememberService(
        db,
        feature_delegation=_delegation_with_settings(
            SimpleNamespace(add_memory=add_memory),
            {
                "access_control.whitelist_enabled": True,
                "access_control.allowed_ids": "someone-else",
            },
        ),
    )

    result = await service.remember(
        group_id="group-a",
        sender_id="user-a",
        content="今天状态怎么样 => 我今天状态不错",
    )

    add_memory.assert_not_awaited()
    assert result.memory_id == 7


@pytest.mark.asyncio
async def test_remember_allowed_when_whitelist_matches_sender():
    db = _FakeDb()
    add_memory = AsyncMock(return_value=42)
    service = RememberService(
        db,
        feature_delegation=_delegation_with_settings(
            SimpleNamespace(add_memory=add_memory),
            {
                "access_control.whitelist_enabled": True,
                "access_control.allowed_ids": "user-a",
            },
        ),
    )

    result = await service.remember(
        group_id="group-a",
        sender_id="user-a",
        content="今天状态怎么样 => 我今天状态不错",
    )

    add_memory.assert_awaited_once()
    assert result.memory_id == 42
