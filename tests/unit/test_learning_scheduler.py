import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.factory import LearningScheduler


def _scheduler(orchestrator):
    plugin = SimpleNamespace(
        plugin_config=SimpleNamespace(learning_interval_hours=6),
        _group_orchestrator=orchestrator,
    )
    scheduler = LearningScheduler(plugin)
    scheduler.is_running = True
    return scheduler


@pytest.mark.asyncio
async def test_learning_scheduler_cycle_sweeps_active_groups():
    orchestrator = SimpleNamespace(
        get_active_groups=AsyncMock(return_value=["g1", "g2"]),
        smart_start_learning_for_group=AsyncMock(),
    )
    scheduler = _scheduler(orchestrator)

    await scheduler.run_cycle()

    orchestrator.get_active_groups.assert_awaited_once_with()
    assert [
        call.args[0]
        for call in orchestrator.smart_start_learning_for_group.await_args_list
    ] == ["g1", "g2"]


@pytest.mark.asyncio
async def test_learning_scheduler_cycle_keeps_going_after_group_error():
    orchestrator = SimpleNamespace(
        get_active_groups=AsyncMock(return_value=["bad", "good"]),
        smart_start_learning_for_group=AsyncMock(
            side_effect=[RuntimeError("boom"), None]
        ),
    )
    scheduler = _scheduler(orchestrator)

    await scheduler.run_cycle()

    assert orchestrator.smart_start_learning_for_group.await_count == 2


@pytest.mark.asyncio
async def test_learning_scheduler_cycle_stops_when_shutdown_requested():
    orchestrator = SimpleNamespace(
        get_active_groups=AsyncMock(return_value=["g1", "g2"]),
        smart_start_learning_for_group=AsyncMock(),
    )
    scheduler = _scheduler(orchestrator)

    async def _stop_after_first(_group_id):
        scheduler.is_running = False

    orchestrator.smart_start_learning_for_group.side_effect = _stop_after_first

    await scheduler.run_cycle()

    assert orchestrator.smart_start_learning_for_group.await_count == 1


@pytest.mark.asyncio
async def test_learning_scheduler_cycle_without_orchestrator_is_noop():
    scheduler = LearningScheduler(
        SimpleNamespace(plugin_config=SimpleNamespace(learning_interval_hours=6))
    )
    scheduler.is_running = True

    await scheduler.run_cycle()


@pytest.mark.asyncio
async def test_learning_scheduler_cycle_survives_group_lookup_failure():
    orchestrator = SimpleNamespace(
        get_active_groups=AsyncMock(side_effect=RuntimeError("db down")),
        smart_start_learning_for_group=AsyncMock(),
    )
    scheduler = _scheduler(orchestrator)

    await scheduler.run_cycle()

    orchestrator.smart_start_learning_for_group.assert_not_awaited()
