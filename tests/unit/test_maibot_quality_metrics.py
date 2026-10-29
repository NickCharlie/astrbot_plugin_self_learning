"""MaiBot 增强质量指标的回归测试。

人格字典不包含 expression_patterns / memory_updates / knowledge_updates，
历史实现直接读取这些字段，导致四个指标永远退化为 0。这里锁定修复后的
行为：指标来自真实学习产物快照，学习落库后再刷新一次。
"""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.core_learning.progressive_learning import (
    ProgressiveLearningService,
)
from self_learning_EterU.services.integration.maibot_adapters import MaiBotQualityMonitor


def _monitor(context=None) -> MaiBotQualityMonitor:
    config = SimpleNamespace(max_messages_per_batch=200)
    db_manager = SimpleNamespace()
    return MaiBotQualityMonitor(config, db_manager, context)


@pytest.mark.unit
def test_growth_metrics_use_real_snapshot_counts():
    monitor = _monitor()

    metrics = monitor._build_quality_metrics(
        {"prompt": "same"},
        {"prompt": "same"},
        snapshot_before={
            "expression_patterns": 3,
            "memory_updates": 5,
            "knowledge_updates": 2,
        },
        snapshot_after={
            "expression_patterns": 8,
            "memory_updates": 5,
            "knowledge_updates": 2,
        },
    )

    assert metrics["expression_pattern_improvement"] == pytest.approx(0.5)
    assert metrics["memory_graph_growth"] == pytest.approx(0.0)
    assert metrics["knowledge_graph_growth"] == pytest.approx(0.0)
    # prompt 未变化时为 0，与三个增长指标一起参与均值，不再用硬编码 0.4 兜底
    assert metrics["overall_quality"] == pytest.approx((0.5 + 0.0 + 0.0 + 0.0) / 4)


@pytest.mark.unit
def test_unavailable_metrics_are_none_not_zero():
    monitor = _monitor()

    metrics = monitor._build_quality_metrics(
        {"prompt": "p"},
        {"prompt": "p"},
        snapshot_before={"expression_patterns": 1, "memory_updates": None, "knowledge_updates": None},
        snapshot_after={"expression_patterns": 1, "memory_updates": None, "knowledge_updates": None},
    )

    assert metrics["memory_graph_growth"] is None
    assert metrics["knowledge_graph_growth"] is None
    assert metrics["expression_pattern_improvement"] == pytest.approx(0.0)
    assert metrics["overall_quality"] == pytest.approx(0.0)


@pytest.mark.unit
def test_prompt_change_scores_even_when_length_is_unchanged():
    monitor = _monitor()

    metrics = monitor._build_quality_metrics(
        {"prompt": "abcdefghij"},
        {"prompt": "abcdefghXY"},
    )

    assert metrics["prompt_improvement"] > 0.0


@pytest.mark.unit
def test_identical_prompt_scores_zero():
    monitor = _monitor()

    metrics = monitor._build_quality_metrics(
        {"prompt": "abcdefghij"},
        {"prompt": "abcdefghij"},
    )

    assert metrics["prompt_improvement"] == 0.0


@pytest.mark.asyncio
async def test_batch_evaluation_refreshes_real_growth(monkeypatch):
    monitor = _monitor()
    snapshots = [
        {
            "expression_patterns": 2,
            "memory_updates": 10,
            "knowledge_updates": 4,
            "memory_source": "local_graph",
        },
        {
            "expression_patterns": 5,
            "memory_updates": 12,
            "knowledge_updates": 4,
            "memory_source": "local_graph",
        },
    ]

    async def fake_collect(group_id):
        return snapshots.pop(0)

    monkeypatch.setattr(monitor, "_collect_learning_snapshot", fake_collect)

    messages = [{"message": "你好呀今天过得怎么样", "group_id": "g1"}]
    result = await monitor.evaluate_learning_batch(
        {"prompt": "人格", "group_id": "g1"},
        {"prompt": "人格", "group_id": "g1"},
        messages,
    )

    # 学习尚未应用时还没有增长
    assert result.data["expression_pattern_improvement"] == pytest.approx(0.0)

    refreshed = await monitor.refresh_learning_impact("g1", result, messages)

    assert refreshed is not None
    assert result.data["expression_pattern_improvement"] == pytest.approx(0.3)
    assert result.data["memory_graph_growth"] == pytest.approx(0.2)
    assert result.data["knowledge_graph_growth"] == pytest.approx(0.0)
    assert result.data["memory_source"] == "local_graph"
    assert result.consistency_score == pytest.approx(refreshed)


@pytest.mark.asyncio
async def test_refresh_requires_before_snapshot(monkeypatch):
    monitor = _monitor()
    monkeypatch.setattr(
        monitor,
        "_collect_learning_snapshot",
        AsyncMock(return_value={"expression_patterns": 5}),
    )

    quality_metrics = SimpleNamespace(data={"overall_quality": 0.0})
    refreshed = await monitor.refresh_learning_impact("g1", quality_metrics, [])

    assert refreshed is None


@pytest.mark.asyncio
async def test_livingmemory_graph_store_counts_memories(monkeypatch):
    monitor = _monitor(context=SimpleNamespace())

    class GraphStore:
        async def get_graph_snapshot(self, **_kwargs):
            return {"memories": [{"memory_id": 1}, {"memory_id": 2}]}

    monkeypatch.setattr(monitor, "_livingmemory_graph_store", lambda: GraphStore())

    count = await monitor._count_livingmemory_memories("g1")

    assert count == 2


@pytest.mark.asyncio
async def test_missing_snapshot_falls_back_to_message_signal(monkeypatch):
    monitor = _monitor()

    async def _none(_group_id):
        return None

    monkeypatch.setattr(monitor, "_collect_learning_snapshot", _none)

    messages = [{"message": "今天聊点什么好呢", "group_id": "g1"}]
    result = await monitor.evaluate_learning_batch({}, {}, messages)

    assert result.data["quality_source"] == "learning_messages"
    assert result.consistency_score == pytest.approx(result.data["overall_quality"])
    assert result.consistency_score > 0


@pytest.mark.asyncio
async def test_livingmemory_total_memories_fallback(monkeypatch):
    monitor = _monitor(context=SimpleNamespace())
    engine = SimpleNamespace(
        get_statistics=AsyncMock(return_value={"total_memories": 128})
    )
    monkeypatch.setattr(monitor, "_livingmemory_graph_store", lambda: None)
    monkeypatch.setattr(monitor, "_livingmemory_backend", lambda: (None, engine))

    count = await monitor._count_livingmemory_memories("g1")

    assert count == 128


@pytest.mark.asyncio
async def test_collect_snapshot_reads_database_counts(monkeypatch):
    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    class FakeSession:
        def __init__(self, counts):
            self._counts = iter(counts)

        async def execute(self, _statement):
            return FakeResult(next(self._counts))

    class FakeSessionContext:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *_args):
            return False

    db_manager = SimpleNamespace(
        get_session=lambda: FakeSessionContext(FakeSession([3, 4, 5]))
    )
    monitor = MaiBotQualityMonitor(
        SimpleNamespace(max_messages_per_batch=200), db_manager
    )
    monkeypatch.setattr(
        monitor, "_count_livingmemory_memories", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(monitor, "_local_memory_node_count", lambda _group_id: 7)

    snapshot = await monitor._collect_learning_snapshot("g1")

    assert snapshot is not None
    assert snapshot["expression_patterns"] == 3
    assert snapshot["knowledge_updates"] == 9
    assert snapshot["memory_updates"] == 7
    assert snapshot["memory_source"] == "local_graph"


@pytest.mark.asyncio
async def test_progressive_learning_refreshes_quality_after_updates():
    refresh = AsyncMock(return_value=0.72)
    service = SimpleNamespace(
        quality_monitor=SimpleNamespace(refresh_learning_impact=refresh)
    )

    score = await ProgressiveLearningService._refresh_quality_after_updates(
        service,
        "g1",
        SimpleNamespace(data={}),
        [{"message": "hello"}],
        0.4,
    )

    assert score == pytest.approx(0.72)
    refresh.assert_awaited_once()
