"""Unit tests for ConfigService schema-driven settings."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import PluginConfig
from statics.messages import FileNames
from webui.services.config_service import ConfigService


def build_container(tmp_path: Path):
    plugin_config = PluginConfig.create_default()
    plugin_config.data_dir = str(tmp_path / "self_learning_data")
    plugin_config.messages_db_path = None
    plugin_config.learning_log_path = None

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

    llm_adapter = Mock()
    llm_adapter.initialize_providers = Mock()

    container = Mock()
    container.plugin_config = plugin_config
    container.factory_manager = factory_manager
    container.llm_adapter = llm_adapter
    return container


@pytest.mark.unit
class TestConfigServiceSchema:
    @pytest.mark.asyncio
    async def test_get_config_schema_includes_full_settings(self, tmp_path):
        container = build_container(tmp_path)
        service = ConfigService(container)

        schema = await service.get_config_schema()

        groups = {group["key"]: group for group in schema["groups"]}
        assert "Filter_Parameters" in groups
        assert "Runtime_Internal_Settings" in groups

        filter_fields = {field["key"] for field in groups["Filter_Parameters"]["fields"]}
        assert "relevance_threshold" in filter_fields

        storage_fields = {field["key"]: field for field in groups["Storage_Settings"]["fields"]}
        assert storage_fields["data_dir"]["restart_required"] is True

        runtime_fields = {field["key"]: field for field in groups["Runtime_Internal_Settings"]["fields"]}
        assert runtime_fields["messages_db_path"]["editable"] is False

        advanced_fields = {field["key"]: field for field in groups["Advanced_Settings"]["fields"]}
        assert advanced_fields["log_level"]["widget"] == "select"
        assert [option["value"] for option in advanced_fields["log_level"]["options"]] == [
            "error",
            "warning",
            "info",
            "debug",
        ]

        v2_fields = {field["key"]: field for field in groups["V2_Architecture_Settings"]["fields"]}
        assert v2_fields["embedding_provider_id"]["widget"] == "provider"
        assert v2_fields["rerank_provider_id"]["widget"] == "provider"

        assert schema["provider_options"][0]["value"] == "provider-a"

    @pytest.mark.asyncio
    async def test_config_schema_covers_all_plugin_config_fields(self, tmp_path):
        container = build_container(tmp_path)
        service = ConfigService(container)

        schema = await service.get_config_schema()

        covered_fields = {
            field["key"]
            for group in schema["groups"]
            for field in group["fields"]
        }
        assert set(PluginConfig.model_fields) <= covered_fields


@pytest.mark.unit
class TestConfigServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_config_persists_and_syncs_paths(self, tmp_path):
        container = build_container(tmp_path)
        service = ConfigService(container)

        new_data_dir = tmp_path / "custom_data"
        success, message, updated = await service.update_config(
            {
                "Storage_Settings": {
                    "data_dir": str(new_data_dir),
                },
                "Database_Settings": {
                    "db_type": "postgresql",
                    "postgresql_host": "db.local",
                    "postgresql_schema": "bot_space",
                },
                "Filter_Parameters": {
                    "relevance_threshold": 0.75,
                },
                "Advanced_Settings": {
                    "log_level": "debug",
                },
            }
        )

        assert success is True
        assert "重启后生效" in message
        assert updated["db_type"] == "postgresql"
        assert updated["relevance_threshold"] == 0.75
        assert updated["log_level"] == "debug"
        assert updated["messages_db_path"].endswith(FileNames.MESSAGES_DB_FILE)
        assert updated["learning_log_path"].endswith(FileNames.LEARNING_LOG_FILE)
        container.llm_adapter.initialize_providers.assert_called_once_with(container.plugin_config)

        config_file = Path(container.plugin_config.data_dir) / FileNames.CONFIG_FILE
        assert config_file.exists()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["db_type"] == "postgresql"
        assert saved["postgresql_schema"] == "bot_space"
        assert saved["relevance_threshold"] == 0.75
        assert saved["log_level"] == "debug"
