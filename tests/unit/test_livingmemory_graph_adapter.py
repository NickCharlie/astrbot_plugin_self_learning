"""LivingMemory 2.8.x graph_store adapter tests.

2.8.0 added ``get_full_graph_snapshot`` (no fixed truncation). The graph
service should use it for large dashboard requests and fall back to the
light snapshot on older stores.
"""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.services.graph_service import GraphService  # noqa: E402


class _GraphStore:
    def __init__(self):
        self.light_calls = []
        self.full_calls = []

    async def get_graph_snapshot(self, **kwargs):
        self.light_calls.append(kwargs)
        return {"nodes": [], "edges": [], "entries": [], "memories": []}

    async def get_full_graph_snapshot(self, **kwargs):
        self.full_calls.append(kwargs)
        return {
            "nodes": [{"id": 1, "label": "Alice"}],
            "edges": [],
            "entries": [],
            "memories": [],
        }


class _OldGraphStore:
    async def get_full_graph_snapshot(self, **_kwargs):
        raise TypeError("full snapshot unsupported")

    async def get_graph_snapshot(self, **_kwargs):
        return {
            "nodes": [{"id": 2, "label": "Bob"}],
            "edges": [],
            "entries": [],
            "memories": [],
        }


def _service() -> GraphService:
    return GraphService(SimpleNamespace(group_id_to_unified_origin={}))


@pytest.mark.asyncio
async def test_large_limit_prefers_full_snapshot():
    service = _service()
    store = _GraphStore()

    snapshot = await service._read_livingmemory_snapshot(store, "g1", 300)

    assert store.full_calls
    assert store.light_calls == []
    assert snapshot["nodes"][0]["label"] == "Alice"

@pytest.mark.asyncio
async def test_default_limit_uses_light_snapshot_with_roomier_budget():
    service = _service()
    store = _GraphStore()

    await service._read_livingmemory_snapshot(store, "g1", 120)

    assert store.full_calls == []
    assert store.light_calls[0]["limit_nodes"] == 120
    assert store.light_calls[0]["limit_memories"] == 30
    assert store.light_calls[0]["limit_entries"] == 120


@pytest.mark.asyncio
async def test_full_snapshot_type_error_falls_back_to_light_in_same_call():
    service = _service()
    store = _OldGraphStore()

    snapshot = await service._read_livingmemory_snapshot(store, "g1", 300)

    assert snapshot["nodes"][0]["label"] == "Bob"


@pytest.mark.unit
def test_global_scope_prefers_livingmemory_global_candidate():
    plugin = SimpleNamespace(
        config_manager=SimpleNamespace(
            get=lambda key, default=None: "global"
        )
    )
    star = SimpleNamespace(star_cls=plugin)
    service = GraphService(
        SimpleNamespace(
            group_id_to_unified_origin={"g1": "umo:g1"},
            feature_delegation=SimpleNamespace(memory_plugin=lambda: star),
        )
    )

    candidates = service._livingmemory_session_candidates("g1")

    assert candidates == ["livingmemory:global", "umo:g1", "g1"]


@pytest.mark.unit
def test_groupless_view_falls_back_to_unfiltered_snapshot():
    service = _service()

    assert service._livingmemory_session_candidates(None) == [None]
