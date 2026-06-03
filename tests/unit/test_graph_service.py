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
async def test_knowledge_graph_prefers_livingmemory_graph_store(tmp_path):
    class GraphStore:
        calls = []

        async def get_graph_snapshot(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "nodes": [
                    {
                        "id": 1,
                        "type": "person",
                        "label": "Alice",
                        "canonical_value": "alice",
                        "entry_count": 2,
                    },
                    {
                        "id": 2,
                        "type": "topic",
                        "label": "Tea",
                        "canonical_value": "tea",
                        "entry_count": 1,
                    },
                ],
                "edges": [
                    {
                        "source": 1,
                        "target": 2,
                        "relation_type": "likes",
                        "weight": 1.5,
                    }
                ],
                "entries": [],
                "memories": [],
            }

    graph_dir = tmp_path / "lightrag" / "group-a"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph_chunk_entity_relation.graphml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph edgedefault="undirected">
    <node id="FallbackOnly"/>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )

    graph_store = GraphStore()
    livingmemory_plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            memory_engine=SimpleNamespace(
                graph_store=graph_store,
                get_statistics=lambda: {"graph_nodes": 2},
            )
        )
    )
    container = SimpleNamespace(
        database_manager=None,
        plugin_config=SimpleNamespace(data_dir=str(tmp_path)),
        v2_integration=None,
        group_id_to_unified_origin={"group-a": "umo:group-a"},
        feature_delegation=SimpleNamespace(
            status=lambda: {
                "memory_delegated": True,
                "memory_plugin": "LivingMemory",
            },
            memory_plugin=lambda: SimpleNamespace(star_cls=livingmemory_plugin),
        ),
    )

    payload = await GraphService(container).get_knowledge_graph(
        group_id="group-a",
        limit=20,
    )

    assert graph_store.calls[0]["session_id"] == "umo:group-a"
    assert payload["type"] == "knowledge"
    assert payload["data_source"] == "livingmemory_graph_store"
    assert payload["source_stats"]["graph_nodes"] == 2
    assert {node["name"] for node in payload["nodes"]} >= {"Alice", "Tea"}
    assert "FallbackOnly" not in {node["name"] for node in payload["nodes"]}
    assert any(link["label"]["formatter"] == "likes" for link in payload["links"])


@pytest.mark.asyncio
async def test_knowledge_graph_falls_back_when_livingmemory_graph_store_empty(tmp_path):
    class EmptyGraphStore:
        async def get_graph_snapshot(self, **_kwargs):
            return {"nodes": [], "edges": [], "entries": [], "memories": []}

    graph_dir = tmp_path / "lightrag" / "group-a"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph_chunk_entity_relation.graphml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="entity_type" attr.type="string"/>
  <key id="d1" for="edge" attr.name="keywords" attr.type="string"/>
  <graph edgedefault="undirected">
    <node id="FallbackAlice"><data key="d0">person</data></node>
    <node id="FallbackTea"><data key="d0">topic</data></node>
    <edge source="FallbackAlice" target="FallbackTea"><data key="d1">fallback-likes</data></edge>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )
    livingmemory_plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            memory_engine=SimpleNamespace(graph_store=EmptyGraphStore())
        )
    )
    container = SimpleNamespace(
        database_manager=None,
        plugin_config=SimpleNamespace(data_dir=str(tmp_path)),
        v2_integration=None,
        group_id_to_unified_origin={"group-a": "umo:group-a"},
        feature_delegation=SimpleNamespace(
            status=lambda: {
                "memory_delegated": True,
                "memory_plugin": "LivingMemory",
            },
            memory_plugin=lambda: SimpleNamespace(star_cls=livingmemory_plugin),
        ),
    )

    payload = await GraphService(container).get_knowledge_graph(
        group_id="group-a",
        limit=20,
    )

    assert payload["type"] == "knowledge"
    assert payload["data_source"] == "self_learning"
    assert payload["groups"] == ["group-a"]
    assert {node["name"] for node in payload["nodes"]} >= {
        "FallbackAlice",
        "FallbackTea",
    }
    assert any(
        link["label"]["formatter"] == "fallback-likes"
        for link in payload["links"]
    )


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


@pytest.mark.asyncio
async def test_memory_graph_reads_livingmemory_graph_store_directly():
    class GraphStore:
        calls = []

        async def get_graph_snapshot(
            self,
            *,
            session_id,
            persona_id,
            limit_memories,
            limit_entries,
            limit_nodes,
            limit_edges,
        ):
            self.calls.append(
                {
                    "session_id": session_id,
                    "persona_id": persona_id,
                    "limit_memories": limit_memories,
                    "limit_entries": limit_entries,
                    "limit_nodes": limit_nodes,
                    "limit_edges": limit_edges,
                }
            )
            return {
                "nodes": [
                    {
                        "id": 1,
                        "type": "person",
                        "label": "Alice",
                        "canonical_value": "alice",
                        "entry_count": 2,
                        "memory_count": 1,
                        "degree": 1,
                    },
                    {
                        "id": 2,
                        "type": "topic",
                        "label": "Tea",
                        "canonical_value": "tea",
                        "entry_count": 1,
                        "memory_count": 1,
                        "degree": 1,
                    },
                ],
                "edges": [
                    {
                        "id": 7,
                        "source": 1,
                        "target": 2,
                        "relation_type": "likes",
                        "memory_id": 42,
                        "weight": 1.5,
                    }
                ],
                "entries": [
                    {
                        "id": 9,
                        "memory_id": 42,
                        "entry_type": "fact",
                        "relation_type": "likes",
                        "content": "Alice likes tea",
                        "session_id": "umo:group-a",
                        "node_ids": [1, 2],
                    }
                ],
                "memories": [
                    {
                        "memory_id": 42,
                        "summary": "Alice likes tea",
                        "session_id": "umo:group-a",
                        "importance": 0.8,
                    }
                ],
            }

    graph_store = GraphStore()
    livingmemory_plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            memory_engine=SimpleNamespace(
                graph_store=graph_store,
                get_statistics=lambda: {
                    "graph_nodes": 2,
                    "graph_edges": 1,
                    "graph_entries": 1,
                },
            )
        )
    )
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": True,
            "memory_plugin": "LivingMemory",
        },
        memory_plugin=lambda: SimpleNamespace(star_cls=livingmemory_plugin),
    )
    container = SimpleNamespace(
        database_manager=None,
        plugin_config=SimpleNamespace(),
        v2_integration=None,
        group_id_to_unified_origin={"group-a": "umo:group-a"},
        feature_delegation=delegation,
    )

    payload = await GraphService(container).get_memory_graph(group_id="group-a", limit=30)

    assert graph_store.calls[0]["session_id"] == "umo:group-a"
    assert payload["data_source"] == "livingmemory_graph_store"
    assert payload["source_stats"]["graph_nodes"] == 2
    assert payload["groups"] == ["umo:group-a"]
    assert {node["name"] for node in payload["nodes"]} >= {
        "Alice",
        "Tea",
        "Alice likes tea",
    }
    assert any(link["label"]["formatter"] == "likes" for link in payload["links"])


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
