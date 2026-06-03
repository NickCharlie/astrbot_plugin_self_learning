"""Integration tests for companion dashboard routes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from quart import Quart

import webui.blueprints.integrations as integrations_module
from webui.blueprints.integrations import integrations_bp


def _star(name, plugin, *, root_dir_name=None):
    return SimpleNamespace(
        name=name,
        display_name=name,
        root_dir_name=root_dir_name or name,
        module_path=f"data.plugins.{root_dir_name or name}.main",
        star_cls=plugin,
    )


@pytest.fixture
async def app(monkeypatch):
    livingmemory_star = _star(
        "LivingMemory",
        SimpleNamespace(config_manager=SimpleNamespace(webui_settings={"enabled": False})),
        root_dir_name="astrbot_plugin_livingmemory",
    )
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": True,
            "memory_plugin": "LivingMemory",
            "reply_delegated": False,
            "reply_plugin": None,
        },
        memory_plugin=lambda: livingmemory_star,
        reply_plugin=lambda: None,
    )
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(),
        webui_config=SimpleNamespace(host="127.0.0.1", port=7833),
        astrbot_core_config={"dashboard": {"enable": True, "host": "0.0.0.0", "port": 6185}},
        feature_delegation=delegation,
    )
    monkeypatch.setattr(integrations_module, "get_container", lambda: container)

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(integrations_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_livingmemory_old_plugin_page_url_redirects_to_astrbot_dashboard(client):
    response = await client.get(
        "/api/plugin/page/content/astrbot_plugin_livingmemory/dashboard/",
    )

    assert response.status_code == 302
    assert response.headers["Location"] == (
        "http://127.0.0.1:6185/api/plugin/page/content/LivingMemory/dashboard/"
    )


@pytest.mark.asyncio
async def test_unknown_plugin_page_url_is_not_claimed_by_self_learning(client):
    response = await client.get("/api/plugin/page/content/unknown/dashboard/")

    assert response.status_code == 404
    data = await response.get_json()
    assert data["success"] is False
