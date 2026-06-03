"""Integration tests for dashboard graph routes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from quart import Quart

import webui.blueprints.graphs as graphs_module
from webui.blueprints.graphs import graphs_bp


@pytest.fixture
async def app(monkeypatch):
    monkeypatch.setattr(
        graphs_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=None),
    )

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(graphs_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_memory_graph_route_returns_echarts_payload(client):
    response = await client.get("/api/graphs/memory")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["type"] == "memory"
    assert "nodes" in data
    assert "links" in data
    assert "categories" in data


@pytest.mark.asyncio
async def test_memory_graph_route_explains_livingmemory_delegation(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        graphs_module,
        "get_container",
        lambda: SimpleNamespace(
            database_manager=None,
            feature_delegation=SimpleNamespace(
                status=lambda: {
                    "memory_delegated": True,
                    "memory_plugin": "LivingMemory",
                    "reply_delegated": False,
                    "reply_plugin": None,
                }
            ),
        ),
    )

    response = await client.get("/api/graphs/memory")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["type"] == "memory"
    assert data["empty_reason"] == "graph_backend_empty"
    assert data["data_source"] == "livingmemory_backend_empty"
    assert "LivingMemory" in data["message"]


@pytest.mark.asyncio
async def test_memory_graph_route_reads_livingmemory_graph_store(
    client,
    monkeypatch,
):
    class GraphStore:
        async def get_graph_snapshot(self, **_kwargs):
            return {
                "nodes": [
                    {
                        "id": 1,
                        "type": "person",
                        "label": "Alice",
                        "canonical_value": "alice",
                        "entry_count": 1,
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
                        "weight": 1,
                    }
                ],
                "entries": [],
                "memories": [
                    {
                        "memory_id": 42,
                        "summary": "Alice likes tea",
                        "session_id": "umo:group-a",
                    }
                ],
            }

    livingmemory_plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            memory_engine=SimpleNamespace(
                graph_store=GraphStore(),
                get_statistics=lambda: (_ for _ in ()).throw(RuntimeError("stats down")),
            )
        )
    )
    monkeypatch.setattr(
        graphs_module,
        "get_container",
        lambda: SimpleNamespace(
            database_manager=None,
            group_id_to_unified_origin={"group-a": "umo:group-a"},
            feature_delegation=SimpleNamespace(
                status=lambda: {
                    "memory_delegated": True,
                    "memory_plugin": "LivingMemory",
                    "reply_delegated": False,
                    "reply_plugin": None,
                },
                memory_plugin=lambda: SimpleNamespace(star_cls=livingmemory_plugin),
            ),
        ),
    )

    response = await client.get("/api/graphs/memory?group_id=group-a")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["data_source"] == "livingmemory_graph_store"
    assert "empty_reason" not in data
    assert {node["name"] for node in data["nodes"]} >= {"Alice", "Tea"}
    assert any(link["label"]["formatter"] == "likes" for link in data["links"])


@pytest.mark.asyncio
async def test_knowledge_graph_route_returns_echarts_payload(client):
    response = await client.get("/api/graphs/knowledge")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["type"] == "knowledge"
    assert "nodes" in data
    assert "links" in data
    assert "categories" in data


@pytest.mark.asyncio
async def test_knowledge_graph_route_reads_livingmemory_graph_store(
    client,
    monkeypatch,
):
    class GraphStore:
        async def get_graph_snapshot(self, **_kwargs):
            return {
                "nodes": [
                    {
                        "id": 1,
                        "type": "person",
                        "label": "Alice",
                        "canonical_value": "alice",
                        "entry_count": 1,
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
                        "weight": 1,
                    }
                ],
                "entries": [],
                "memories": [],
            }

    livingmemory_plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            memory_engine=SimpleNamespace(graph_store=GraphStore())
        )
    )
    monkeypatch.setattr(
        graphs_module,
        "get_container",
        lambda: SimpleNamespace(
            database_manager=None,
            group_id_to_unified_origin={"group-a": "umo:group-a"},
            feature_delegation=SimpleNamespace(
                status=lambda: {
                    "memory_delegated": True,
                    "memory_plugin": "LivingMemory",
                    "reply_delegated": False,
                    "reply_plugin": None,
                },
                memory_plugin=lambda: SimpleNamespace(star_cls=livingmemory_plugin),
            ),
        ),
    )

    response = await client.get("/api/graphs/knowledge?group_id=group-a")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["type"] == "knowledge"
    assert data["data_source"] == "livingmemory_graph_store"
    assert {node["name"] for node in data["nodes"]} >= {"Alice", "Tea"}
    assert any(link["label"]["formatter"] == "likes" for link in data["links"])
