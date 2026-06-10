"""Integration tests for jargon dashboard routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from quart import Quart

import webui.blueprints.jargon as jargon_module
from webui.blueprints.jargon import jargon_bp


@pytest.fixture
async def app(monkeypatch):
    database_manager = SimpleNamespace(
        search_jargon=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "content": "已确认",
                    "is_jargon": True,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 2,
                    "content": "已驳回",
                    "is_jargon": False,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 3,
                    "content": "待审",
                    "is_jargon": False,
                    "is_complete": False,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
            ]
        )
    )
    monkeypatch.setattr(
        jargon_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=database_manager),
    )

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(jargon_bp)
    app.database_manager = database_manager
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_jargon_search_route_passes_global_filter(client, app):
    response = await client.get(
        "/api/jargon/search?keyword=%E6%9C%AF%E8%AF%AD&confirmed=true&filter=global"
    )

    assert response.status_code == 200
    app.database_manager.search_jargon.assert_awaited_once_with(
        "术语",
        chat_id=None,
        confirmed_only=True,
        pending_only=False,
        global_only=True,
        local_only=False,
    )


@pytest.mark.asyncio
async def test_jargon_list_search_respects_confirmed_false(client):
    response = await client.get("/api/jargon/list?keyword=term&confirmed=false")

    assert response.status_code == 200
    data = await response.get_json()
    assert [item["term"] for item in data["jargon_list"]] == ["已驳回", "待审"]


@pytest.mark.asyncio
async def test_jargon_list_search_respects_pending_filter(client):
    response = await client.get("/api/jargon/list?keyword=term&pending=true")

    assert response.status_code == 200
    data = await response.get_json()
    assert [item["term"] for item in data["jargon_list"]] == ["待审"]


@pytest.mark.asyncio
async def test_jargon_batch_review_route_calls_service(client, monkeypatch):
    calls = []

    class _FakeJargonService:
        def __init__(self, container):
            self.container = container

        async def batch_review_jargon(self, jargon_ids, action, meaning=None):
            calls.append((jargon_ids, action, meaning))
            return {
                "success": True,
                "message": "批量审查完成",
                "details": {"success_count": len(jargon_ids), "failed_count": 0},
            }

    monkeypatch.setattr(jargon_module, "JargonService", _FakeJargonService)

    response = await client.post(
        "/api/jargon/batch_review",
        json={"jargon_ids": [7, 8], "action": "reject", "meaning": "ignored"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert calls == [([7, 8], "reject", "ignored")]


@pytest.mark.asyncio
async def test_jargon_batch_delete_route_calls_service(client, monkeypatch):
    calls = []

    class _FakeJargonService:
        def __init__(self, container):
            self.container = container

        async def batch_delete_jargon(self, jargon_ids):
            calls.append(jargon_ids)
            return {
                "success": True,
                "message": "批量删除完成",
                "details": {"success_count": len(jargon_ids), "failed_count": 0},
            }

    monkeypatch.setattr(jargon_module, "JargonService", _FakeJargonService)

    response = await client.post(
        "/api/jargon/batch_delete",
        json={"jargon_ids": [7, 8]},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert calls == [[7, 8]]
