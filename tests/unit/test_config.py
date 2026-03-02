"""
Unit tests for PluginConfig

Tests the plugin configuration management including:
- Default value initialization
- Configuration creation from dict
- Configuration validation
- File persistence (save/load)
- Boundary value verification
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from config import PluginConfig


@pytest.mark.unit
@pytest.mark.config
class TestPluginConfigDefaults:
    """Test PluginConfig default value initialization."""

    def test_create_default_instance(self):
        """Test creating a default PluginConfig instance."""
        config = PluginConfig()

        assert config.enable_message_capture is True
        assert config.enable_auto_learning is True
        assert config.enable_realtime_learning is False
        assert config.enable_web_interface is True
        assert config.web_interface_port == 7833
        assert config.web_interface_host == "0.0.0.0"

    def test_create_default_classmethod(self):
        """Test the create_default classmethod."""
        config = PluginConfig.create_default()

        assert isinstance(config, PluginConfig)
        assert config.learning_interval_hours == 6
        assert config.min_messages_for_learning == 50
        assert config.max_messages_per_batch == 200

    def test_default_learning_parameters(self):
        """Test default learning parameter values."""
        config = PluginConfig()

        assert config.message_min_length == 5
        assert config.message_max_length == 500
        assert config.confidence_threshold == 0.7
        assert config.relevance_threshold == 0.6
        assert config.style_analysis_batch_size == 100
        assert config.style_update_threshold == 0.6

    def test_default_database_settings(self):
        """Test default database configuration values."""
        config = PluginConfig()

        assert config.db_type == "sqlite"
        assert config.mysql_host == "localhost"
        assert config.mysql_port == 3306
        assert config.postgresql_host == "localhost"
        assert config.postgresql_port == 5432
        assert config.max_connections == 10

    def test_default_affection_settings(self):
        """Test default affection system configuration."""
        config = PluginConfig()

        assert config.enable_affection_system is True
        assert config.max_total_affection == 250
        assert config.max_user_affection == 100
        assert config.affection_decay_rate == 0.95

    def test_default_provider_ids_none(self):
        """Test provider IDs default to None."""
        config = PluginConfig()

        assert config.filter_provider_id is None
        assert config.refine_provider_id is None
        assert config.reinforce_provider_id is None
        assert config.embedding_provider_id is None
        assert config.rerank_provider_id is None

    def test_sqlalchemy_always_true(self):
        """Test that use_sqlalchemy is always True (hardcoded)."""
        config = PluginConfig()
        assert config.use_sqlalchemy is True


@pytest.mark.unit
@pytest.mark.config
class TestPluginConfigFromDict:
    """Test PluginConfig creation from configuration dict."""

    def test_create_from_basic_config(self):
        """Test creating config from a basic configuration dict."""
        raw_config = {
            'Self_Learning_Basic': {
                'enable_message_capture': False,
                'enable_auto_learning': False,
                'web_interface_port': 8080,
            }
        }

        config = PluginConfig.create_from_config(raw_config, data_dir="/tmp/test")

        assert config.enable_message_capture is False
        assert config.enable_auto_learning is False
        assert config.web_interface_port == 8080
        assert config.data_dir == "/tmp/test"

    def test_create_from_config_with_model_settings(self):
        """Test config creation with model configuration."""
        raw_config = {
            'Model_Configuration': {
                'filter_provider_id': 'provider_1',
                'refine_provider_id': 'provider_2',
                'reinforce_provider_id': 'provider_3',
            }
        }

        config = PluginConfig.create_from_config(raw_config, data_dir="/tmp/test")

        assert config.filter_provider_id == 'provider_1'
        assert config.refine_provider_id == 'provider_2'
        assert config.reinforce_provider_id == 'provider_3'

    def test_create_from_config_missing_data_dir(self):
        """Test config creation with empty data_dir uses fallback."""
        config = PluginConfig.create_from_config({}, data_dir="")

        assert config.data_dir == "./data/self_learning_data"

    def test_create_from_config_with_database_settings(self):
        """Test config creation with database settings."""
        raw_config = {
            'Database_Settings': {
                'db_type': 'mysql',
                'mysql_host': '192.168.1.100',
                'mysql_port': 3307,
                'mysql_user': 'admin',
                'mysql_password': 'secret',
                'mysql_database': 'test_db',
            }
        }

        config = PluginConfig.create_from_config(raw_config, data_dir="/tmp/test")

        assert config.db_type == 'mysql'
        assert config.mysql_host == '192.168.1.100'
        assert config.mysql_port == 3307
        assert config.mysql_user == 'admin'
        assert config.mysql_database == 'test_db'

    def test_create_from_config_with_v2_settings(self):
        """Test config creation with v2 architecture settings."""
        raw_config = {
            'V2_Architecture_Settings': {
                'embedding_provider_id': 'embed_provider',
                'rerank_provider_id': 'rerank_provider',
                'knowledge_engine': 'lightrag',
                'memory_engine': 'mem0',
            }
        }

        config = PluginConfig.create_from_config(raw_config, data_dir="/tmp/test")

        assert config.embedding_provider_id == 'embed_provider'
        assert config.rerank_provider_id == 'rerank_provider'
        assert config.knowledge_engine == 'lightrag'
        assert config.memory_engine == 'mem0'

    def test_create_from_empty_config(self):
        """Test config creation from empty dict uses all defaults."""
        config = PluginConfig.create_from_config({}, data_dir="/tmp/test")

        assert config.enable_message_capture is True
        assert config.learning_interval_hours == 6
        assert config.db_type == 'sqlite'

    def test_extra_fields_ignored(self):
        """Test that extra/unknown fields are ignored."""
        config = PluginConfig(
            unknown_field_1="value1",
            unknown_field_2=42,
        )
        assert not hasattr(config, 'unknown_field_1')


@pytest.mark.unit
@pytest.mark.config
class TestPluginConfigValidation:
    """Test PluginConfig validation logic."""

    def test_valid_config_no_errors(self):
        """Test validation of a valid default config."""
        config = PluginConfig(
            filter_provider_id="provider_1",
            refine_provider_id="provider_2",
        )
        errors = config.validate_config()

        # Should have no blocking errors (may have warnings for reinforce)
        blocking_errors = [e for e in errors if not e.startswith(" ")]
        assert len(blocking_errors) == 0

    def test_invalid_learning_interval(self):
        """Test validation catches invalid learning interval."""
        config = PluginConfig(learning_interval_hours=0)
        errors = config.validate_config()

        assert any("学习间隔必须大于0" in e for e in errors)

    def test_invalid_min_messages(self):
        """Test validation catches invalid min messages for learning."""
        config = PluginConfig(min_messages_for_learning=0)
        errors = config.validate_config()

        assert any("最少学习消息数量必须大于0" in e for e in errors)

    def test_invalid_max_batch_size(self):
        """Test validation catches invalid max batch size."""
        config = PluginConfig(max_messages_per_batch=-1)
        errors = config.validate_config()

        assert any("每批最大消息数量必须大于0" in e for e in errors)

    def test_invalid_message_length_range(self):
        """Test validation catches min_length >= max_length."""
        config = PluginConfig(message_min_length=500, message_max_length=100)
        errors = config.validate_config()

        assert any("最小长度必须小于最大长度" in e for e in errors)

    def test_invalid_confidence_threshold(self):
        """Test validation catches confidence threshold out of range."""
        config = PluginConfig(confidence_threshold=1.5)
        errors = config.validate_config()

        assert any("置信度阈值必须在0-1之间" in e for e in errors)

    def test_invalid_style_threshold(self):
        """Test validation catches style update threshold out of range."""
        config = PluginConfig(style_update_threshold=-0.1)
        errors = config.validate_config()

        assert any("风格更新阈值必须在0-1之间" in e for e in errors)

    def test_no_providers_configured(self):
        """Test validation warns when no providers are configured."""
        config = PluginConfig(
            filter_provider_id=None,
            refine_provider_id=None,
            reinforce_provider_id=None,
        )
        errors = config.validate_config()

        assert any("至少需要配置一个模型提供商ID" in e for e in errors)

    def test_partial_providers_configured(self):
        """Test validation with only some providers configured."""
        config = PluginConfig(
            filter_provider_id="provider_1",
            refine_provider_id=None,
            reinforce_provider_id=None,
        )
        errors = config.validate_config()

        # Should have warnings but no blocking errors
        blocking_errors = [e for e in errors if not e.startswith(" ")]
        assert len(blocking_errors) == 0


@pytest.mark.unit
@pytest.mark.config
class TestPluginConfigSerialization:
    """Test PluginConfig serialization and deserialization."""

    def test_to_dict(self):
        """Test converting config to dict."""
        config = PluginConfig(
            enable_message_capture=False,
            web_interface_port=9090,
        )

        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict['enable_message_capture'] is False
        assert config_dict['web_interface_port'] == 9090
        assert 'learning_interval_hours' in config_dict

    def test_save_to_file_success(self):
        """Test saving config to file."""
        config = PluginConfig()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            filepath = f.name

        try:
            result = config.save_to_file(filepath)

            assert result is True
            assert os.path.exists(filepath)

            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            assert saved_data['enable_message_capture'] is True
        finally:
            os.unlink(filepath)

    def test_load_from_file_success(self):
        """Test loading config from existing file."""
        config_data = {
            'enable_message_capture': False,
            'web_interface_port': 9999,
            'learning_interval_hours': 12,
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(config_data, f)
            filepath = f.name

        try:
            loaded_config = PluginConfig.load_from_file(filepath)

            assert loaded_config.enable_message_capture is False
            assert loaded_config.web_interface_port == 9999
            assert loaded_config.learning_interval_hours == 12
        finally:
            os.unlink(filepath)

    def test_load_from_nonexistent_file(self):
        """Test loading config from nonexistent file returns defaults."""
        loaded_config = PluginConfig.load_from_file("/nonexistent/path.json")

        assert loaded_config.enable_message_capture is True
        assert loaded_config.learning_interval_hours == 6

    def test_load_from_file_with_data_dir(self):
        """Test loading config with explicit data_dir override."""
        config_data = {'enable_message_capture': True}

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(config_data, f)
            filepath = f.name

        try:
            loaded_config = PluginConfig.load_from_file(
                filepath, data_dir="/custom/data/dir"
            )

            assert loaded_config.data_dir == "/custom/data/dir"
        finally:
            os.unlink(filepath)

    def test_load_from_corrupt_file(self):
        """Test loading config from corrupt file returns defaults."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            f.write("this is not valid json {{{")
            filepath = f.name

        try:
            loaded_config = PluginConfig.load_from_file(filepath)

            # Should return default config
            assert loaded_config.enable_message_capture is True
        finally:
            os.unlink(filepath)
