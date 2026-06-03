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
async def test_knowledge_graph_route_returns_echarts_payload(client):
    response = await client.get("/api/graphs/knowledge")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["type"] == "knowledge"
    assert "nodes" in data
    assert "links" in data
    assert "categories" in data
