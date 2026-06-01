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
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


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
