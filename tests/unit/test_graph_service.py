from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.integration.knowledge_graph_manager import (
    KnowledgeGraphManager,
)
from self_learning_EterU.services.state.enhanced_memory_graph_manager import (
    EnhancedMemoryGraphManager,
)
from self_learning_EterU.webui.services.graph_service import GraphService


@pytest.mark.asyncio
async def test_knowledge_graph_reads_lightrag_graphml(tmp_path):
    graph_dir = tmp_path / "lightrag" / "group-a"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph_chunk_entity_relation.graphml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="entity_type" attr.type="string"/>
  <key id="d1" for="node" attr.name="description" attr.type="string"/>
  <key id="d2" for="edge" attr.name="keywords" attr.type="string"/>
  <graph edgedefault="undirected">
    <node id="Alice"><data key="d0">person</data><data key="d1">speaker</data></node>
    <node id="Tea"><data key="d0">topic</data><data key="d1">drink</data></node>
    <edge source="Alice" target="Tea"><data key="d2">likes</data></edge>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )
    container = SimpleNamespace(
        database_manager=None,
        plugin_config=SimpleNamespace(data_dir=str(tmp_path)),
        v2_integration=None,
        group_id_to_unified_origin={},
    )

    payload = await GraphService(container).get_knowledge_graph(limit=20)

    assert payload["groups"] == ["group-a"]
    assert {node["name"] for node in payload["nodes"]} >= {"Alice", "Tea"}
    assert payload["links"][0]["label"]["formatter"] == "likes"
    assert payload["stats"]["nodes"] == 2
    assert payload["stats"]["links"] == 1


@pytest.mark.asyncio
async def test_memory_graph_reads_active_mem0_manager(monkeypatch):
    monkeypatch.setattr(EnhancedMemoryGraphManager, "_instance", None)

    class MemoryStore:
        def get_all(self, *, agent_id):
            assert agent_id == "group-a"
            return {
                "results": [
                    {
                        "id": "mem-1",
                        "memory": "Alice likes tea",
                        "user_id": "alice",
                        "score": 0.8,
                    }
                ]
            }

    v2 = SimpleNamespace(
        _memory_manager=SimpleNamespace(_memory=MemoryStore()),
        _ingestion_buffer={},
    )
    container = SimpleNamespace(
        database_manager=None,
        plugin_config=SimpleNamespace(),
        v2_integration=v2,
        group_id_to_unified_origin={"group-a": "origin"},
    )

    payload = await GraphService(container).get_memory_graph(limit=20)

    assert payload["groups"] == ["group-a"]
    assert any(node["id"] == "mem0:group-a:mem-1" for node in payload["nodes"])
    assert any(link["target"] == "mem0:group-a:mem-1" for link in payload["links"])
    assert payload["stats"]["nodes"] > 0


def test_memory_graph_singleton_accepts_late_dependencies(monkeypatch):
    monkeypatch.setattr(EnhancedMemoryGraphManager, "_instance", None)
    first = EnhancedMemoryGraphManager.get_instance()
    db_manager = object()

    second = EnhancedMemoryGraphManager.get_instance(db_manager=db_manager)

    assert second is first
    assert second.db_manager is db_manager

    third = EnhancedMemoryGraphManager.get_instance()
    assert third is first
    assert third.db_manager is db_manager


def test_knowledge_graph_singleton_accepts_late_dependencies(monkeypatch):
    monkeypatch.setattr(KnowledgeGraphManager, "_instance", None)
    first = KnowledgeGraphManager.get_instance()
    db_manager = object()
    llm_adapter = object()

    first.configure(db_manager=db_manager, llm_adapter=llm_adapter)

    assert first.db_manager is db_manager
    assert first.llm_adapter is llm_adapter

    second = KnowledgeGraphManager.get_instance()
    assert second is first
    assert second.db_manager is db_manager
    assert second.llm_adapter is llm_adapter
