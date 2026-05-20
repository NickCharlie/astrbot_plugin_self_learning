"""Integration tests for config blueprint routes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from quart import Quart

import webui.blueprints.config as config_module
from config import PluginConfig
from webui.blueprints.config import config_bp


def build_container(tmp_path: Path):
    plugin_config = PluginConfig.create_default()
    plugin_config.data_dir = str(tmp_path / "self_learning_data")

    provider_meta = SimpleNamespace(
        id="provider-a",
        provider_type=SimpleNamespace(value="llm"),
    )
    provider = Mock()
    provider.meta = Mock(return_value=provider_meta)

    context = Mock()
    context.get_all_providers = Mock(return_value=[provider])

    service_factory = Mock()
    service_factory.context = context

    factory_manager = Mock()
    factory_manager.get_service_factory = Mock(return_value=service_factory)

    container = Mock()
    container.plugin_config = plugin_config
    container.factory_manager = factory_manager
    container.llm_adapter = Mock()
    return container


@pytest.fixture
async def app(tmp_path, monkeypatch):
    container = build_container(tmp_path)
    monkeypatch.setattr(config_module, "get_container", lambda: container)

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(config_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_config_schema_route_returns_groups(client):
    response = await client.get("/api/config/schema")

    assert response.status_code == 200
    data = await response.get_json()
    assert "groups" in data
    assert any(group["key"] == "Database_Settings" for group in data["groups"])
    assert any(
        field["key"] == "relevance_threshold"
        for group in data["groups"]
        for field in group["fields"]
    )
    assert any(
        field["key"] == "log_level" and field["widget"] == "select"
        for group in data["groups"]
        for field in group["fields"]
    )
