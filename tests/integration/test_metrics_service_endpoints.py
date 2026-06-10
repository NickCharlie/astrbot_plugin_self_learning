"""Integration tests for MetricsService-backed metrics endpoints.

These guard against the regression where MetricsService called methods that no
longer existed after the architecture refactor (calculate_metrics /
get_diversity_metrics / get_affection_metrics), making the endpoints always
return zeroed fallback data with a logged AttributeError.
"""

from types import SimpleNamespace

import pytest
from quart import Quart

import webui.blueprints.metrics as metrics_module
from webui.blueprints.metrics import metrics_bp


class DummyDatabaseManager:
    async def get_detailed_metrics(self, group_id=None):
        return {
            "messages": {"raw": 100, "filtered": 40, "bot": 10},
            "learning": {
                "persona_reviews": 4,
                "style_reviews": 3,
                "batches": 2,
                "style_patterns": 6,
            },
            "group_id": group_id,
        }

    async def get_all_user_affections(self, group_id):
        return [
            {"user_id": "u1", "affection_level": 80},
            {"user_id": "u2", "affection_level": 50},
            {"user_id": "u3", "affection_level": 20},
        ]


class DummyIntelligenceMetricsService:
    async def calculate_learning_efficiency(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            overall_efficiency=72.5,
            message_filter_rate=40.0,
            content_refine_quality=0.0,
            style_learning_progress=60.0,
            persona_update_quality=50.0,
            jargon_learning_score=0.0,
            social_relation_score=0.0,
            affection_score=30.0,
            active_strategies_count=0,
        )


@pytest.fixture
async def app(monkeypatch):
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"

    container = SimpleNamespace(
        database_manager=DummyDatabaseManager(),
        intelligence_metrics_service=DummyIntelligenceMetricsService(),
    )
    monkeypatch.setattr(metrics_module, "get_container", lambda: container)

    app.register_blueprint(metrics_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_intelligence_metrics_uses_learning_efficiency(client):
    response = await client.get("/api/intelligence_metrics?group_id=g1")

    assert response.status_code == 200
    data = await response.get_json()

    assert "error" not in data
    assert data["overall_score"] == 72.5
    assert data["dimensions"]["message_filter_rate"] == 40.0
    assert data["dimensions"]["affection_score"] == 30.0
    assert data["dimensions"]["active_strategies_count"] == 0
    assert data["trends"] == []


@pytest.mark.asyncio
async def test_affection_metrics_computed_from_user_affections(client):
    response = await client.get("/api/affection_metrics?group_id=g1")

    assert response.status_code == 200
    data = await response.get_json()

    assert "error" not in data
    assert data["total_users"] == 3
    assert data["average_affection"] == 50.0
    assert data["high_affection_count"] == 1  # level 80 >= 70
    assert data["low_affection_count"] == 1  # level 20 <= 30
    # buckets partition every user exactly once
    assert sum(b["count"] for b in data["distribution"]) == 3


@pytest.mark.asyncio
async def test_diversity_metrics_estimated_from_style_patterns(client):
    response = await client.get("/api/diversity_metrics?group_id=g1")

    assert response.status_code == 200
    data = await response.get_json()

    assert "error" not in data
    assert data["style_diversity"] == 12  # 6 patterns * 2
    assert data["vocabulary_diversity"] == 0
    assert data["topic_diversity"] == 0
    assert data["total_score"] == 4.0  # (12 + 0 + 0) / 3
