"""Integration tests for the Self Learning Hub API."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from quart import Quart

import webui.blueprints.hub as hub_module
import webui.middleware.hub_aspects as hub_aspects_module
from webui.blueprints.hub import hub_bp
from webui.middleware.hub_aspects import HubApiError
from webui.services.hub_service import HubService


def assert_no_store_headers(response):
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


@dataclass
class RememberResult:
    memory_id: int = 11
    expression_saved: bool = True
    exemplar_id: int | None = 7
    style_review_id: int = 3


class DummyRememberService:
    def __init__(self):
        self.calls = []

    async def remember(self, *, group_id: str, sender_id: str, content: str):
        self.calls.append(
            {"group_id": group_id, "sender_id": sender_id, "content": content}
        )
        return RememberResult()


class DummyDatabaseManager:
    def __init__(self):
        self.saved_messages = []

    async def save_raw_message(self, message):
        self.saved_messages.append(message)
        return 99

    async def get_approved_few_shots(self, group_id, limit=5):
        return [f"{group_id}:{limit}:few-shot"]


class DummySocialContextInjector:
    async def format_complete_context(self, **kwargs):
        return f"social:{kwargs['group_id']}:{kwargs['user_id']}"


class DummyV2Integration:
    async def get_enhanced_context(self, query, group_id, top_k=5):
        return {
            "query": query,
            "group_id": group_id,
            "top_k": top_k,
            "few_shot_examples": ["v2-example"],
        }

    async def process_message(self, message, group_id):
        return {
            "processed": True,
            "group_id": group_id,
            "message_type": type(message).__name__,
        }


class DummyJargonService:
    async def check_and_explain_jargon(self, text, chat_id):
        return f"jargon:{chat_id}:{text}"


class DummyProgressiveLearning:
    def __init__(self):
        self.started = []
        self.learning_active = {"group-a": True}

    async def start_learning(self, group_id):
        self.started.append(group_id)
        return {"group_id": group_id, "started": True}


class DummyReviewService:
    def __init__(self):
        self.calls = []

    async def get_pending_persona_updates(self, limit=50, offset=0):
        self.calls.append(("list", limit, offset))
        return {"updates": [{"id": "r1"}], "total": 1, "status": "pending"}

    async def review_persona_update(self, review_id, decision, comment, modified_content):
        self.calls.append(("decide", review_id, decision, comment, modified_content))
        return True, "ok"


@pytest.fixture
async def app(monkeypatch):
    remember_service = DummyRememberService()
    progressive_learning = DummyProgressiveLearning()
    review_service = DummyReviewService()
    database_manager = DummyDatabaseManager()
    plugin_instance = SimpleNamespace(
        remember_service=remember_service,
        social_context_injector=DummySocialContextInjector(),
        jargon_query_service=DummyJargonService(),
        message_collector=None,
        background_tasks=set(),
    )
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(
            enable_api_auth=False,
            api_key="test-key",
            rerank_top_k=9,
            include_social_relations=True,
            include_affection_info=True,
            include_mood_info=True,
            enable_expression_patterns=True,
            enable_goal_driven_chat=False,
        ),
        plugin_instance=plugin_instance,
        database_manager=database_manager,
        database_degraded=False,
        database_start_error=None,
        progressive_learning=progressive_learning,
        v2_integration=DummyV2Integration(),
        feature_delegation=SimpleNamespace(status=lambda: {}),
        persona_updater=review_service,
    )

    monkeypatch.setattr(hub_module, "get_container", lambda: container)
    monkeypatch.setattr(hub_aspects_module, "get_container", lambda: container)
    monkeypatch.setattr(
        "webui.services.hub_service.PersonaReviewService",
        lambda _container: review_service,
    )
    monkeypatch.setattr(
        "webui.services.hub_service.IntegrationService",
        lambda _container: SimpleNamespace(get_status=lambda: {"integration": "ok"}),
    )

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(hub_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_hub_manifest_exposes_mvc_and_aop_contract(client):
    response = await client.get("/api/hub/v1/manifest")

    assert response.status_code == 200
    assert_no_store_headers(response)
    data = await response.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "self-learning-hub"
    assert data["data"]["base_path"] == "/api/hub/v1"
    assert data["data"]["architecture"]["mvc"]["controller"] == "webui.blueprints.hub"
    assert data["data"]["architecture"]["aop"]["implementation"] == "webui.middleware.hub_aspects"
    assert any(item["path"] == "/api/hub/v1/messages/ingest" for item in data["data"]["endpoints"])
    assert data["data"]["examples"]["remember"]["content"].startswith("A:")


@pytest.mark.asyncio
async def test_hub_status_is_available_without_auth(client):
    response = await client.get("/api/hub/v1/status")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["data"]["healthy"] is True
    assert data["data"]["integration"] == {"integration": "ok"}


@pytest.mark.asyncio
async def test_hub_context_builds_prompt_ready_payload(client):
    response = await client.post(
        "/api/hub/v1/context",
        json={
            "group_id": "group-a",
            "user_id": "user-a",
            "query": "怎么回复更自然？",
            "include": {"social": True, "jargon": True, "few_shots": True, "v2": True},
            "top_k": 4,
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    payload = data["data"]
    assert payload["group_id"] == "group-a"
    assert payload["context_text"]
    assert any(part["type"] == "social" for part in payload["parts"])
    assert payload["few_shots"] == ["group-a:4:few-shot"]
    assert payload["v2"]["top_k"] == 4


@pytest.mark.asyncio
async def test_hub_remember_links_memory_expression_and_review(client):
    response = await client.post(
        "/api/hub/v1/memories/remember",
        json={
            "group_id": "group-a",
            "sender_id": "user-a",
            "content": "A: 今天忙吗？\nB: 还好，刚处理完。",
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["message"] == "remembered"
    assert data["data"]["memory_id"] == 11
    assert data["data"]["expression_saved"] is True
    assert data["data"]["style_review_id"] == 3


@pytest.mark.asyncio
async def test_hub_ingest_message_supports_message_data_fallback(client):
    response = await client.post(
        "/api/hub/v1/messages/ingest",
        json={
            "group_id": "group-a",
            "sender_id": "user-a",
            "sender_name": "Alice",
            "message": "hello hub",
            "platform": "companion",
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["message"] == "ingested"
    assert data["data"]["collected"] is True
    assert data["data"]["v2"]["message_type"] == "MessageData"
    assert data["data"]["message"]["platform"] == "companion"


@pytest.mark.asyncio
async def test_hub_learning_trigger_runs_background_and_wait_modes(client):
    async_response = await client.post(
        "/api/hub/v1/learning/trigger",
        json={"group_id": "group-a"},
    )
    wait_response = await client.post(
        "/api/hub/v1/learning/trigger",
        json={"group_id": "group-a", "wait": True},
    )

    async_data = await async_response.get_json()
    wait_data = await wait_response.get_json()

    assert async_response.status_code == 200
    assert async_data["data"]["started"] is True
    assert async_data["data"]["completed"] is False
    assert wait_response.status_code == 200
    assert wait_data["data"]["completed"] is True
    assert wait_data["data"]["result"]["started"] is True


@pytest.mark.asyncio
async def test_hub_reviews_and_decision_routes(client):
    list_response = await client.get("/api/hub/v1/reviews?limit=2&offset=1")
    assert list_response.status_code == 200
    list_data = await list_response.get_json()
    assert list_data["success"] is True
    assert list_data["data"]["status"] == "pending"

    decision_response = await client.post(
        "/api/hub/v1/reviews/review-1/decision",
        json={"decision": "approve", "comment": "ok"},
    )

    assert decision_response.status_code == 200
    decision_data = await decision_response.get_json()
    assert decision_data["data"]["success"] is True
    assert decision_data["data"]["review_id"] == "review-1"
    assert decision_data["data"]["decision"] == "approve"


@pytest.mark.asyncio
async def test_hub_auth_rejects_invalid_api_key_when_enabled(monkeypatch, app):
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    container = hub_module.get_container()
    container.plugin_config.enable_api_auth = True

    response = await app.test_client().get(
        "/api/hub/v1/status",
        headers={"X-Self-Learning-Key": "wrong"},
    )

    assert response.status_code == 401
    assert_no_store_headers(response)
    body = await response.get_data(as_text=True)
    assert "wrong" not in body
    assert "test-key" not in body
    data = await response.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_hub_auth_accepts_valid_bearer_without_echoing_api_key(app):
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    container = hub_module.get_container()
    container.plugin_config.enable_api_auth = True

    response = await app.test_client().get(
        "/api/hub/v1/status",
        headers={"Authorization": "Bearer test-key"},
    )

    assert response.status_code == 200
    assert_no_store_headers(response)
    body = await response.get_data(as_text=True)
    assert "test-key" not in body


@pytest.mark.asyncio
async def test_hub_api_error_wraps_as_stable_envelope():
    error = HubApiError("bad input", 422, "invalid_request")
    assert error.status_code == 422
    assert error.code == "invalid_request"
