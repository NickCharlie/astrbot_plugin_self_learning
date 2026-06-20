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


def assert_no_store_headers(response):
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def build_container(tmp_path: Path):
    plugin_config = PluginConfig.create_default()
    plugin_config.data_dir = str(tmp_path / "self_learning_data")

    provider_meta = SimpleNamespace(
        id="chat-a",
        model="gpt-test",
        provider_type=SimpleNamespace(value="chat_completion"),
    )
    provider = Mock()
    provider.meta = Mock(return_value=provider_meta)

    embedding_meta = SimpleNamespace(
        id="embed-a",
        model="text-embedding-test",
        provider_type=SimpleNamespace(value="embedding"),
    )
    embedding_provider = Mock()
    embedding_provider.meta = Mock(return_value=embedding_meta)

    rerank_meta = SimpleNamespace(
        id="rerank-a",
        model="rerank-test",
        provider_type=SimpleNamespace(value="rerank"),
    )
    rerank_provider = Mock()
    rerank_provider.meta = Mock(return_value=rerank_meta)

    context = Mock()
    context.get_all_providers = Mock(return_value=[provider])
    context.get_all_embedding_providers = Mock(return_value=[embedding_provider])
    context.provider_manager = SimpleNamespace(
        rerank_provider_insts=[rerank_provider],
        inst_map={
            "chat-a": provider,
            "embed-a": embedding_provider,
            "rerank-a": rerank_provider,
        },
    )

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
    assert_no_store_headers(response)
    data = await response.get_json()
    assert "groups" in data
    assert "warnings" in data
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
    assert data["provider_options_by_type"]["embedding"][0]["value"] == "embed-a"
    assert data["provider_options_by_type"]["rerank"][0]["value"] == "rerank-a"


@pytest.mark.asyncio
async def test_config_post_then_schema_refresh_returns_saved_values(client):
    response = await client.post(
        "/api/config",
        json={
            "Target_Settings": {
                "target_qq_list": ["10001", "group_20002"],
            },
            "Learning_Parameters": {
                "learning_interval_hours": 2,
            },
            "Integration_Settings": {
                "delegate_memory_to_livingmemory": False,
            },
        },
    )

    assert response.status_code == 200

    refresh = await client.get("/api/config/schema")

    assert refresh.status_code == 200
    data = await refresh.get_json()
    assert data["config"]["target_qq_list"] == ["10001", "group_20002"]
    assert data["config"]["learning_interval_hours"] == 2
    assert data["config"]["delegate_memory_to_livingmemory"] is False

    fields = {
        field["key"]: field
        for group in data["groups"]
        for field in group["fields"]
    }
    assert fields["target_qq_list"]["value"] == ["10001", "group_20002"]
    assert fields["learning_interval_hours"]["value"] == 2
    assert fields["delegate_memory_to_livingmemory"]["value"] is False


@pytest.mark.asyncio
async def test_config_responses_redact_sensitive_fields(client):
    secret_payload = {
        "API_Settings": {
            "api_key": "super-secret-api-key",
            "enable_api_auth": True,
        },
        "Database_Settings": {
            "mysql_password": "mysql-secret",
            "postgresql_password": "postgres-secret",
        },
    }

    update = await client.post("/api/config", json=secret_payload)
    assert update.status_code == 200
    assert_no_store_headers(update)
    update_body = await update.get_data(as_text=True)
    assert "super-secret-api-key" not in update_body
    assert "mysql-secret" not in update_body
    assert "postgres-secret" not in update_body
    update_data = await update.get_json()
    assert update_data["new_config"]["api_key"] == ""
    assert update_data["new_config"]["mysql_password"] == ""
    assert update_data["new_config"]["postgresql_password"] == ""

    config_response = await client.get("/api/config")
    assert config_response.status_code == 200
    assert_no_store_headers(config_response)
    config_body = await config_response.get_data(as_text=True)
    assert "super-secret-api-key" not in config_body
    assert "mysql-secret" not in config_body
    assert "postgres-secret" not in config_body
    config_data = await config_response.get_json()
    assert config_data["api_key"] == ""
    assert config_data["mysql_password"] == ""
    assert config_data["postgresql_password"] == ""

    schema_response = await client.get("/api/config/schema")
    assert schema_response.status_code == 200
    assert_no_store_headers(schema_response)
    schema_body = await schema_response.get_data(as_text=True)
    assert "super-secret-api-key" not in schema_body
    assert "mysql-secret" not in schema_body
    assert "postgres-secret" not in schema_body
    schema_data = await schema_response.get_json()
    assert schema_data["config"]["api_key"] == ""
    fields = {
        field["key"]: field
        for group in schema_data["groups"]
        for field in group["fields"]
    }
    for key in ("api_key", "mysql_password", "postgresql_password"):
        assert fields[key]["widget"] == "password"
        assert fields[key]["secret"] is True
        assert fields[key]["value"] == ""
