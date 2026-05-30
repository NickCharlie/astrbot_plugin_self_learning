from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from quart import Quart

import webui.blueprints.jargon as jargon_module
from webui.blueprints.jargon import jargon_bp


@pytest.fixture
async def app(monkeypatch):
    database_manager = SimpleNamespace(search_jargon=AsyncMock(return_value=[]))
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
