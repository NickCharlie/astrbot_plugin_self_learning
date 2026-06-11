"""Unit tests for ConfigService schema-driven settings."""

from __future__ import annotations

from collections import UserDict
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import PluginConfig
from statics.messages import FileNames
from webui.services.config_service import ConfigService


class SaveableConfig(UserDict):
    def __init__(self, *args, **kwargs):
        self.config_path = kwargs.pop("config_path", None)
        super().__init__(*args, **kwargs)
        self.save_calls = 0
        self.saved_payloads = []

    def save_config(self, replace_config=None):
        self.save_calls += 1
        if replace_config is not None:
            self.data.clear()
            self.data.update(replace_config)
            self.saved_payloads.append(replace_config)
        else:
            self.saved_payloads.append(dict(self.data))
        if self.config_path:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.config_path).write_text(
                json.dumps(self.data),
                encoding="utf-8",
            )


def build_container(tmp_path: Path):
    plugin_config = PluginConfig.create_default()
    plugin_config.data_dir = str(tmp_path / "self_learning_data")
    plugin_config.messages_db_path = None
    plugin_config.learning_log_path = None

    chat_meta = SimpleNamespace(
        id="chat-a",
        model="gpt-test",
        provider_type=SimpleNamespace(value="chat_completion"),
    )
    chat_provider = Mock()
    chat_provider.meta = Mock(return_value=chat_meta)

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
    context.get_all_providers = Mock(return_value=[chat_provider])
    context.get_all_embedding_providers = Mock(return_value=[embedding_provider])
    context.provider_manager = SimpleNamespace(
        provider_insts=[chat_provider],
        embedding_provider_insts=[embedding_provider],
        rerank_provider_insts=[rerank_provider],
        inst_map={
            "chat-a": chat_provider,
            "embed-a": embedding_provider,
            "rerank-a": rerank_provider,
        },
    )

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
    container.astrbot_config = SaveableConfig(
        {
            "Target_Settings": {
                "target_qq_list": [],
                "target_blacklist": [],
            },
            "Learning_Parameters": {
                "learning_interval_hours": plugin_config.learning_interval_hours,
                "max_messages_per_batch": plugin_config.max_messages_per_batch,
            },
            "Style_Analysis": {
                "style_update_threshold": plugin_config.style_update_threshold,
            },
            "Filter_Parameters": {
                "relevance_threshold": plugin_config.relevance_threshold,
            },
        }
    )
    container.plugin_instance = SimpleNamespace(
        plugin_config=plugin_config,
        qq_filter=SimpleNamespace(target_qq_list=[], blacklist=[]),
        progressive_learning=SimpleNamespace(
            batch_size=plugin_config.max_messages_per_batch,
            learning_interval=plugin_config.learning_interval_hours * 3600,
            quality_threshold=plugin_config.style_update_threshold,
        ),
    )
    return container


@pytest.mark.unit
class TestConfigServiceSchema:
    def test_astrbot_plugin_schema_uses_plain_log_level_options(self):
        """AstrBot plugin page renders object options as [object Object]."""
        schema_path = Path(__file__).resolve().parents[2] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        options = schema["Advanced_Settings"]["items"]["log_level"]["options"]

        assert options == ["error", "warning", "info", "debug"]
        assert all(isinstance(option, str) for option in options)

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
        assert runtime_fields["enable_llm_hooks"]["widget"] == "toggle"
        assert runtime_fields["enable_llm_hooks"]["value"] is False

        basic_fields = {field["key"]: field for field in groups["Self_Learning_Basic"]["fields"]}
        assert basic_fields["enable_webui_password"]["widget"] == "toggle"
        assert basic_fields["enable_webui_password"]["value"] is False

        maibot_fields = {field["key"]: field for field in groups["MaiBot_Enhancement"]["fields"]}
        assert maibot_fields["enable_realtime_expression_learning"]["widget"] == "toggle"
        assert maibot_fields["enable_realtime_expression_learning"]["value"] is False

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
        assert v2_fields["embedding_provider_id"]["options"][0]["value"] == "embed-a"
        assert v2_fields["embedding_provider_id"]["provider_type"] == "embedding"
        assert v2_fields["embedding_provider_id"]["provider_type_label"] == "Embedding"
        assert v2_fields["rerank_provider_id"]["options"][0]["value"] == "rerank-a"
        assert v2_fields["rerank_provider_id"]["provider_type"] == "rerank"
        assert v2_fields["rerank_provider_id"]["provider_type_label"] == "Reranker"

        model_fields = {field["key"]: field for field in groups["Model_Configuration"]["fields"]}
        assert model_fields["filter_provider_id"]["options"][0]["value"] == "chat-a"
        assert model_fields["filter_provider_id"]["provider_type"] == "chat_completion"
        assert model_fields["filter_provider_id"]["provider_type_label"] == "聊天模型"

        assert {option["value"] for option in schema["provider_options"]} == {
            "chat-a",
            "embed-a",
            "rerank-a",
        }
        assert schema["provider_options_by_type"]["embedding"][0]["value"] == "embed-a"
        assert schema["provider_options_by_type"]["rerank"][0]["value"] == "rerank-a"

    @pytest.mark.asyncio
    async def test_provider_schema_uses_astrbot_provider_config_classification(self, tmp_path):
        plugin_config = PluginConfig.create_default()
        plugin_config.data_dir = str(tmp_path / "self_learning_data")

        context = Mock()
        context.get_all_providers = Mock(return_value=[])
        context.provider_manager = SimpleNamespace(
            provider_insts=[],
            embedding_provider_insts=[],
            rerank_provider_insts=[],
            inst_map={},
            provider_sources_config=[
                {"id": "openai_embedding", "provider_type": "embedding"},
                {"id": "bailian_rerank", "provider_type": "rerank"},
            ],
            providers_config=[
                {
                    "id": "embed-config",
                    "provider_source_id": "openai_embedding",
                    "embedding_model": "text-embedding-3-large",
                },
                {
                    "id": "rerank-config",
                    "provider_source_id": "bailian_rerank",
                    "rerank_model": "qwen3-rerank",
                },
                {
                    "id": "chat-config",
                    "provider_type": "chat_completion",
                    "model": "gpt-4o-mini",
                },
            ],
        )

        service_factory = Mock()
        service_factory.context = context
        factory_manager = Mock()
        factory_manager.get_service_factory = Mock(return_value=service_factory)

        container = Mock()
        container.plugin_config = plugin_config
        container.factory_manager = factory_manager

        schema = await ConfigService(container).get_config_schema()
        groups = {group["key"]: group for group in schema["groups"]}
        v2_fields = {field["key"]: field for field in groups["V2_Architecture_Settings"]["fields"]}
        model_fields = {field["key"]: field for field in groups["Model_Configuration"]["fields"]}

        assert [option["value"] for option in v2_fields["embedding_provider_id"]["options"]] == ["embed-config"]
        assert [option["value"] for option in v2_fields["rerank_provider_id"]["options"]] == ["rerank-config"]
        assert [option["value"] for option in model_fields["filter_provider_id"]["options"]] == ["chat-config"]
        assert schema["provider_options_by_type"]["embedding"][0]["provider_type_label"] == "Embedding"
        assert schema["provider_options_by_type"]["rerank"][0]["provider_type_label"] == "Reranker"

    def test_provider_option_builders_share_metadata_shape(self):
        provider_meta = SimpleNamespace(
            id="embed-live",
            model="text-embedding-test",
            provider_type=SimpleNamespace(value="embedding"),
        )
        provider = Mock()
        provider.meta = Mock(return_value=provider_meta)

        live_option = ConfigService._provider_option(provider)
        config_option = ConfigService._provider_option_from_config(
            {
                "id": "embed-config",
                "provider_type": "embedding",
                "embedding_model": "text-embedding-test",
            },
            {},
        )

        assert set(live_option) == set(config_option)
        assert live_option["provider_type"] == "embedding"
        assert live_option["provider_type_label"] == "Embedding"
        assert config_option["provider_type"] == "embedding"
        assert config_option["provider_type_label"] == "Embedding"

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

    @pytest.mark.asyncio
    async def test_config_schema_refresh_imports_newer_plugin_page_config(self, tmp_path):
        container = build_container(tmp_path)
        config_file = Path(container.plugin_config.data_dir) / FileNames.CONFIG_FILE
        container.plugin_config.save_to_file(str(config_file))
        old_time = config_file.stat().st_mtime - 10
        config_file.touch()
        os.utime(config_file, (old_time, old_time))

        astrbot_path = tmp_path / "astrbot_plugin_self_learning_config.json"
        container.astrbot_config = SaveableConfig(
            {
                "Target_Settings": {
                    "target_qq_list": ["plugin-page"],
                    "target_blacklist": ["blocked-from-plugin"],
                },
                "Learning_Parameters": {
                    "learning_interval_hours": 3,
                    "max_messages_per_batch": container.plugin_config.max_messages_per_batch,
                },
            },
            config_path=astrbot_path,
        )
        container.astrbot_config.save_config(dict(container.astrbot_config))

        schema = await ConfigService(container).get_config_schema()

        assert schema["config"]["target_qq_list"] == ["plugin-page"]
        assert schema["config"]["target_blacklist"] == ["blocked-from-plugin"]
        assert schema["config"]["learning_interval_hours"] == 3

        fields = {
            field["key"]: field
            for group in schema["groups"]
            for field in group["fields"]
        }
        assert fields["target_qq_list"]["value"] == ["plugin-page"]
        assert fields["learning_interval_hours"]["value"] == 3

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["target_qq_list"] == ["plugin-page"]
        assert saved["learning_interval_hours"] == 3

    @pytest.mark.asyncio
    async def test_config_schema_refresh_prefers_grouped_realtime_plugin_page_values(self, tmp_path):
        container = build_container(tmp_path)
        config_file = Path(container.plugin_config.data_dir) / FileNames.CONFIG_FILE
        container.plugin_config.save_to_file(str(config_file))
        old_time = config_file.stat().st_mtime - 10
        config_file.touch()
        os.utime(config_file, (old_time, old_time))

        astrbot_path = tmp_path / "astrbot_plugin_self_learning_config.json"
        container.astrbot_config = SaveableConfig(
            {
                "Self_Learning_Basic": {
                    "enable_realtime_learning": True,
                    "enable_realtime_llm_filter": True,
                    "enable_webui_password": True,
                },
                "enable_realtime_learning": False,
                "enable_realtime_llm_filter": False,
            },
            config_path=astrbot_path,
        )
        container.astrbot_config.save_config(dict(container.astrbot_config))

        schema = await ConfigService(container).get_config_schema()

        assert schema["config"]["enable_realtime_learning"] is True
        assert schema["config"]["enable_realtime_llm_filter"] is True

        fields = {
            field["key"]: field
            for group in schema["groups"]
            for field in group["fields"]
        }
        assert fields["enable_realtime_learning"]["value"] is True
        assert fields["enable_realtime_llm_filter"]["value"] is True

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["enable_realtime_learning"] is True
        assert saved["enable_realtime_llm_filter"] is True

    @pytest.mark.asyncio
    async def test_config_schema_refresh_pushes_newer_webui_config_to_plugin_page(self, tmp_path):
        container = build_container(tmp_path)
        container.plugin_config.target_qq_list = ["webui-saved"]
        container.plugin_config.learning_interval_hours = 4

        config_file = Path(container.plugin_config.data_dir) / FileNames.CONFIG_FILE
        container.plugin_config.save_to_file(str(config_file))

        astrbot_path = tmp_path / "astrbot_plugin_self_learning_config.json"
        container.astrbot_config.config_path = str(astrbot_path)
        container.astrbot_config.save_config(dict(container.astrbot_config))
        old_time = config_file.stat().st_mtime - 10
        os.utime(astrbot_path, (old_time, old_time))

        schema = await ConfigService(container).get_config_schema()

        assert schema["config"]["target_qq_list"] == ["webui-saved"]
        assert schema["config"]["learning_interval_hours"] == 4
        assert container.astrbot_config["Target_Settings"]["target_qq_list"] == [
            "webui-saved",
        ]
        assert container.astrbot_config["Learning_Parameters"]["learning_interval_hours"] == 4
        assert container.astrbot_config.save_calls == 2
        assert container.astrbot_config.saved_payloads[-1]["Target_Settings"]["target_qq_list"] == [
            "webui-saved",
        ]

        await ConfigService(container).get_config_schema()

        assert container.astrbot_config.save_calls == 2


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

    @pytest.mark.asyncio
    async def test_update_config_syncs_webui_changes_to_plugin_page_config_and_runtime(self, tmp_path):
        container = build_container(tmp_path)
        container.astrbot_config["enable_realtime_learning"] = False
        container.astrbot_config["enable_realtime_llm_filter"] = False
        service = ConfigService(container)

        success, message, updated = await service.update_config(
            {
                "Self_Learning_Basic": {
                    "enable_realtime_learning": True,
                    "enable_realtime_llm_filter": True,
                    "enable_webui_password": True,
                },
                "Target_Settings": {
                    "target_qq_list": ["10001", "group_20002"],
                    "target_blacklist": ["blocked"],
                },
                "Learning_Parameters": {
                    "learning_interval_hours": 2,
                    "max_messages_per_batch": 25,
                    "expression_learning_min_interval_seconds": 120,
                },
                "Runtime_Internal_Settings": {
                    "enable_llm_hooks": True,
                },
                "Style_Analysis": {
                    "style_update_threshold": 0.72,
                },
                "Filter_Parameters": {
                    "relevance_threshold": 0.68,
                },
            }
        )

        assert success is True
        assert "已同步到插件设置页" in message
        assert updated["target_qq_list"] == ["10001", "group_20002"]
        assert updated["target_blacklist"] == ["blocked"]
        assert updated["learning_interval_hours"] == 2
        assert updated["enable_realtime_learning"] is True
        assert updated["enable_realtime_llm_filter"] is True
        assert updated["enable_webui_password"] is True
        assert updated["enable_llm_hooks"] is True
        assert updated["expression_learning_min_interval_seconds"] == 120

        assert container.astrbot_config["Self_Learning_Basic"]["enable_realtime_learning"] is True
        assert container.astrbot_config["Self_Learning_Basic"]["enable_realtime_llm_filter"] is True
        assert container.astrbot_config["Self_Learning_Basic"]["enable_webui_password"] is True
        assert container.astrbot_config["Target_Settings"]["target_qq_list"] == [
            "10001",
            "group_20002",
        ]
        assert container.astrbot_config["Target_Settings"]["target_blacklist"] == ["blocked"]
        assert container.astrbot_config["Learning_Parameters"]["learning_interval_hours"] == 2
        assert container.astrbot_config["Learning_Parameters"]["max_messages_per_batch"] == 25
        assert container.astrbot_config["Learning_Parameters"]["expression_learning_min_interval_seconds"] == 120
        assert container.astrbot_config["Runtime_Internal_Settings"]["enable_llm_hooks"] is True
        assert container.astrbot_config["Style_Analysis"]["style_update_threshold"] == 0.72
        assert container.astrbot_config["Filter_Parameters"]["relevance_threshold"] == 0.68
        assert "enable_realtime_learning" not in container.astrbot_config
        assert "enable_realtime_llm_filter" not in container.astrbot_config
        assert container.astrbot_config.save_calls == 1
        assert "enable_realtime_learning" not in container.astrbot_config.saved_payloads[-1]
        assert "enable_realtime_llm_filter" not in container.astrbot_config.saved_payloads[-1]

        assert container.plugin_instance.plugin_config is container.plugin_config
        assert container.plugin_instance.qq_filter.target_qq_list == ["10001", "group_20002"]
        assert container.plugin_instance.qq_filter.blacklist == ["blocked"]
        assert container.plugin_instance.progressive_learning.batch_size == 25
        assert container.plugin_instance.progressive_learning.learning_interval == 7200
        assert container.plugin_instance.progressive_learning.quality_threshold == 0.72
