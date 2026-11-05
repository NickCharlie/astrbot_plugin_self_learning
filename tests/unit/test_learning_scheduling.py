"""Automatic scheduling must use the configuration after pending reads finish."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from self_learning_EterU.services.learning.group_orchestrator import GroupLearningOrchestrator


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("disabled_flag", ["enable_auto_learning", "enable_style_learning"])
async def test_automatic_group_start_rechecks_switch_changed_while_awaiting_statistics(disabled_flag):
    config = SimpleNamespace(
        enable_auto_learning=True, enable_style_learning=True,
        learning_interval_hours=1, min_messages_for_learning=10,
    )
    reading = asyncio.Event()
    resume = asyncio.Event()

    async def read_statistics(group_id):
        reading.set()
        await resume.wait()
        return {"unprocessed_messages": 10}

    progressive = SimpleNamespace(start_learning=AsyncMock(return_value=True))
    orchestrator = GroupLearningOrchestrator(
        config, SimpleNamespace(get_statistics=read_statistics), progressive,
        qq_filter=None, db_manager=None,
    )
    pending_start = asyncio.create_task(orchestrator.smart_start_learning_for_group("group-a"))
    await reading.wait()
    setattr(config, disabled_flag, False)
    resume.set()
    await pending_start

    assert orchestrator.learning_tasks == {} and orchestrator._last_learning_start == {}
    progressive.start_learning.assert_not_awaited()

    setattr(config, disabled_flag, True)
    await orchestrator.smart_start_learning_for_group("group-a")
    await asyncio.gather(*list(orchestrator.learning_tasks.values()))
    progressive.start_learning.assert_awaited_once_with("group-a")
