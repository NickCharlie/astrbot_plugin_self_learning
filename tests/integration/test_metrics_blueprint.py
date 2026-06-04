"""Integration tests for metrics blueprint routes."""

from types import SimpleNamespace

import pytest
from quart import Quart

import webui.blueprints.metrics as metrics_module
from webui.blueprints.metrics import metrics_bp


class DummyDatabaseManager:
    async def get_messages_statistics(self):
        return {"total_messages": 8, "filtered_messages": 4}

    async def get_style_learning_statistics(self):
        return {"approved_reviews": 2, "total_reviews": 3}

    async def get_expression_patterns_statistics(self):
        return {"total_patterns": 5}

    async def get_learning_performance_history(self, group_id):
        return [
            {"quality_score": 0.8, "success": True},
            {"quality_score": 0.4, "success": False},
        ]


class DummyCacheManager:
    def get_hit_rates(self):
        return {
            "general": {"hits": 3, "misses": 1, "hit_rate": 0.75},
            "memory": {"hits": 0, "misses": 2, "hit_rate": 0.0},
        }


@pytest.fixture
async def app(monkeypatch):
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"

    container = SimpleNamespace(
        database_manager=DummyDatabaseManager(),
        llm_adapter=None,
        progressive_learning=SimpleNamespace(learning_active={"g1": True, "g2": False}),
        perf_collector=None,
    )
    monkeypatch.setattr(metrics_module, "get_container", lambda: container)
    monkeypatch.setattr(metrics_module, "_get_cache_manager_instance", lambda: DummyCacheManager())

    app.register_blueprint(metrics_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_metrics_api_returns_cache_hit_rates_directly(client):
    response = await client.get("/api/metrics")

    assert response.status_code == 200
    data = await response.get_json()

    assert data["cache_hit_rates"] == {
        "general": {
            "hits": 3,
            "misses": 1,
            "total_queries": 4,
            "hit_rate": 0.75,
        },
        "memory": {
            "hits": 0,
            "misses": 2,
            "total_queries": 2,
            "hit_rate": 0.0,
        },
    }
    assert data["cache_hit_summary"] == {
        "available": True,
        "total_hits": 3,
        "total_misses": 3,
        "total_queries": 6,
        "hit_rate": 0.5,
    }
