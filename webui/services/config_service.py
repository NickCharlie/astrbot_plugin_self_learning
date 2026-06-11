"""
配置服务 - 处理插件配置相关业务逻辑
"""
from __future__ import annotations

import json
import os
from collections.abc import MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from astrbot.api import logger
from pydantic import ValidationError

from .auth_service import (
    AuthService,
    INITIAL_WEBUI_PASSWORD_ENV_VAR,
    validate_password_strength,
)

try:
    from ...statics.messages import FileNames
    from ...utils.logging_utils import apply_astrbot_log_level
except ImportError:
    from statics.messages import FileNames
    from utils.logging_utils import apply_astrbot_log_level


@lru_cache(maxsize=1)
def _load_schema_definition() -> Dict[str, Any]:
    """Load the editable config schema from the repository root."""
    schema_path = Path(__file__).resolve().parents[2] / "_conf_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


_EXTRA_SCHEMA_DEFINITION: Dict[str, Dict[str, Any]] = {
    "Filter_Parameters": {
        "items": {
            "relevance_threshold": {
                "description": "相关性阈值",
                "type": "float",
                "hint": "消息与学习目标的相关性阈值，0-1之间，越高越严格",
                "default": 0.6,
            },
        },
    },
    "MaiBot_Enhancement": {
        "description": "MaiBot 增强",
        "hint": "启用表达模式、记忆图和知识图谱等扩展能力",
        "items": {
            "enable_maibot_features": {
                "description": "启用 MaiBot 增强功能",
                "type": "bool",
                "hint": "开启后会启用 MaiBot 风格的扩展功能总开关",
                "default": True,
            },
            "enable_expression_patterns": {
                "description": "启用表达模式学习",
                "type": "bool",
                "hint": "学习并维护群聊中的表达模式和常见句式",
                "default": True,
            },
            "enable_realtime_expression_learning": {
                "description": "实时表达方式学习",
                "type": "bool",
                "hint": "实时学习关闭时，是否仍按消息增量触发表达方式学习。默认关闭以避免旁听群聊时产生高频 LLM 调用和审查记录",
                "default": False,
            },
            "enable_memory_graph": {
                "description": "启用记忆图系统",
                "type": "bool",
                "hint": "开启记忆关系图与关联记忆能力",
                "default": True,
            },
            "enable_knowledge_graph": {
                "description": "启用知识图谱",
                "type": "bool",
                "hint": "开启知识关系图谱与实体关联增强",
                "default": True,
            },
            "enable_time_decay": {
                "description": "启用时间衰减",
                "type": "bool",
                "hint": "让旧数据随时间自动弱化权重",
                "default": True,
            },
        },
    },
    "Persona_Evolution_Settings": {
        "description": "人格演化",
        "hint": "控制人格合并、自动应用和更新备份",
        "items": {
            "persona_merge_strategy": {
                "description": "人格合并策略",
                "type": "string",
                "hint": "控制人格更新时的合并方式",
                "default": "smart",
                "options": [
                    {"value": "replace", "label": "替换"},
                    {"value": "append", "label": "追加"},
                    {"value": "prepend", "label": "前置"},
                    {"value": "smart", "label": "智能"},
                ],
            },
            "max_mood_imitation_dialogs": {
                "description": "最大对话风格模仿数量",
                "type": "int",
                "hint": "单次模仿训练最多处理的对话轮数",
                "default": 20,
            },
            "enable_persona_evolution": {
                "description": "启用人格演化跟踪",
                "type": "bool",
                "hint": "开启后会记录人格变化轨迹并参与后续更新",
                "default": True,
            },
            "persona_compatibility_threshold": {
                "description": "人格兼容性阈值",
                "type": "float",
                "hint": "用于判断更新内容是否与当前人格兼容",
                "default": 0.6,
            },
            "use_persona_manager_updates": {
                "description": "使用 PersonaManager 更新",
                "type": "bool",
                "hint": "开启后优先通过 PersonaManager 进行人格更新",
                "default": True,
            },
            "auto_apply_persona_updates": {
                "description": "自动应用人格更新",
                "type": "bool",
                "hint": "仅在 PersonaManager 更新模式下生效",
                "default": True,
            },
            "persona_update_backup_enabled": {
                "description": "启用人格更新备份",
                "type": "bool",
                "hint": "更新前自动创建备份，降低误操作风险",
                "default": True,
            },
        },
    },
    "Runtime_Internal_Settings": {
        "description": "运行与内部",
        "hint": "运行时注入、内存清理和内部路径",
        "items": {
            "llm_hook_injection_target": {
                "description": "LLM Hook 注入目标",
                "type": "string",
                "hint": "控制注入到 system_prompt 还是 prompt",
                "default": "system_prompt",
                "options": [
                    {"value": "system_prompt", "label": "system_prompt"},
                    {"value": "prompt", "label": "prompt"},
                ],
            },
            "enable_llm_hooks": {
                "description": "启用 LLM Hook 上下文注入",
                "type": "bool",
                "hint": "开启后每次回复前会并行拉取社交、记忆、黑话、few-shot 等上下文；默认关闭以避免高频模型调用",
                "default": False,
            },
            "use_sqlalchemy": {
                "description": "强制使用 SQLAlchemy ORM",
                "type": "bool",
                "hint": "当前版本固定为 true，用于统一 SQLite / MySQL / PostgreSQL 表结构",
                "default": True,
                "_readonly": True,
            },
            "enable_memory_cleanup": {
                "description": "启用记忆自动清理",
                "type": "bool",
                "hint": "开启后会定期清理过旧或低重要度的记忆数据",
                "default": True,
            },
            "memory_cleanup_days": {
                "description": "记忆保留天数",
                "type": "int",
                "hint": "低于该天数阈值的旧记忆会被清理",
                "default": 30,
            },
            "memory_importance_threshold": {
                "description": "记忆重要性阈值",
                "type": "float",
                "hint": "低于该阈值的重要性记忆会被视为可清理",
                "default": 0.3,
            },
            "shutdown_step_timeout": {
                "description": "关停步骤超时",
                "type": "int",
                "hint": "每个关停步骤的最大等待时间（秒）",
                "default": 8,
            },
            "task_cancel_timeout": {
                "description": "任务取消超时",
                "type": "int",
                "hint": "后台任务取消时的等待超时（秒）",
                "default": 3,
            },
            "service_stop_timeout": {
                "description": "服务停止超时",
                "type": "int",
                "hint": "单个服务停止时的等待超时（秒）",
                "default": 5,
            },
            "llm_hook_context_timeout": {
                "description": "LLM Hook 上下文超时",
                "type": "float",
                "hint": "LLM Hook 读取单个上下文源的最大等待时间（秒）",
                "default": 3.0,
            },
            "messages_db_path": {
                "description": "消息数据库路径",
                "type": "string",
                "hint": "自动生成的消息数据库路径，通常无需修改",
                "default": None,
                "_readonly": True,
            },
            "learning_log_path": {
                "description": "学习日志路径",
                "type": "string",
                "hint": "自动生成的学习日志路径，通常无需修改",
                "default": None,
                "_readonly": True,
            },
            "total_messages_collected": {
                "description": "累计消息数",
                "type": "int",
                "hint": "当前运行周期内累计收集到的消息数量",
                "default": 0,
                "_readonly": True,
            },
        },
    },
}

_ENUM_FIELD_OPTIONS: Dict[str, List[Dict[str, str]]] = {
    "db_type": [
        {"value": "postgresql", "label": "PostgreSQL"},
        {"value": "sqlite", "label": "SQLite"},
        {"value": "mysql", "label": "MySQL"},
    ],
    "knowledge_engine": [
        {"value": "legacy", "label": "legacy"},
        {"value": "lightrag", "label": "lightrag"},
    ],
    "memory_engine": [
        {"value": "legacy", "label": "legacy"},
        {"value": "mem0", "label": "mem0"},
    ],
    "lightrag_query_mode": [
        {"value": "naive", "label": "naive"},
        {"value": "local", "label": "local"},
        {"value": "global", "label": "global"},
        {"value": "hybrid", "label": "hybrid"},
        {"value": "mix", "label": "mix"},
    ],
    "context_injection_position": [
        {"value": "start", "label": "start"},
        {"value": "end", "label": "end"},
    ],
    "log_level": [
        {"value": "error", "label": "error"},
        {"value": "warning", "label": "warning"},
        {"value": "info", "label": "info"},
        {"value": "debug", "label": "debug"},
    ],
}

_PROVIDER_TYPE_ALIASES = {
    "chat": "chat_completion",
    "llm": "chat_completion",
    "chat_completion": "chat_completion",
    "embedding": "embedding",
    "embed": "embedding",
    "rerank": "rerank",
    "reranker": "rerank",
}

_PROVIDER_TYPE_LABELS = {
    "chat_completion": "聊天模型",
    "embedding": "Embedding",
    "rerank": "Reranker",
}

_RESTART_REQUIRED_KEYS = {
    "data_dir",
    "db_type",
    "mysql_host",
    "mysql_port",
    "mysql_user",
    "mysql_password",
    "mysql_database",
    "postgresql_host",
    "postgresql_port",
    "postgresql_user",
    "postgresql_password",
    "postgresql_database",
    "postgresql_schema",
    "enable_web_interface",
    "web_interface_host",
    "web_interface_port",
    "use_sqlalchemy",
}


class ConfigService:
    """配置服务"""

    def __init__(self, container):
        self.container = container
        self.plugin_config = container.plugin_config

    def _get_container_attr(self, name: str, default: Any = None) -> Any:
        """Read explicitly assigned container attributes without creating Mock children."""
        try:
            attrs = vars(self.container)
        except TypeError:
            attrs = {}
        return attrs.get(name, default)

    def _set_container_attr(self, name: str, value: Any) -> None:
        try:
            setattr(self.container, name, value)
        except (AttributeError, TypeError):
            logger.debug(f"写入容器属性失败: {name}", exc_info=True)

    def _get_config_file_path(self) -> str:
        data_dir = getattr(self.plugin_config, "data_dir", None) if self.plugin_config else None
        if isinstance(data_dir, (str, os.PathLike)) and os.fspath(data_dir):
            return os.path.join(os.fspath(data_dir), FileNames.CONFIG_FILE)
        try:
            from ...config import DEFAULT_DATA_DIR
        except ImportError:
            from config import DEFAULT_DATA_DIR
        return os.path.join(DEFAULT_DATA_DIR, FileNames.CONFIG_FILE)

    def _get_astrbot_config(self) -> Optional[MutableMapping[str, Any]]:
        astrbot_config = self._get_container_attr("astrbot_config")
        plugin = self._get_container_attr("plugin_instance")
        if astrbot_config is None and plugin is not None:
            astrbot_config = getattr(plugin, "config", None)
        if isinstance(astrbot_config, MutableMapping):
            return astrbot_config
        return None

    def _flatten_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        grouped: Dict[str, Any] = {}
        direct: Dict[str, Any] = {}

        for key, value in payload.items():
            if isinstance(value, dict):
                grouped.update(self._flatten_payload(value))
            else:
                direct[key] = value

        # AstrBot's grouped plugin-page config is authoritative over stale top-level compatibility keys.
        return {**direct, **grouped}

    def _merged_schema_definition(self) -> Dict[str, Any]:
        return self._merge_schema_definitions(
            _load_schema_definition(),
            self._collect_extra_schema(),
        )

    @staticmethod
    def _plain_mapping(mapping: MutableMapping[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for key, value in mapping.items():
            if isinstance(value, MutableMapping):
                payload[key] = dict(value)
            else:
                payload[key] = value
        return payload

    def _astrbot_config_is_newer(self, astrbot_config: MutableMapping[str, Any]) -> bool:
        astrbot_path = getattr(astrbot_config, "config_path", None)
        if not astrbot_path:
            return False

        config_file = self._get_config_file_path()
        if not os.path.exists(os.fspath(astrbot_path)):
            return False
        if not os.path.exists(config_file):
            return True

        return os.path.getmtime(os.fspath(astrbot_path)) > os.path.getmtime(config_file)

    @staticmethod
    def _file_mtime_signature(path: Any) -> Optional[float]:
        if not path:
            return None
        try:
            return os.path.getmtime(os.fspath(path))
        except OSError:
            return None

    @staticmethod
    def _payload_signature(payload: Dict[str, Any]) -> str:
        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    def _config_source_signature(
        self,
        astrbot_config: MutableMapping[str, Any],
    ) -> Tuple[Optional[float], Optional[float], str, str]:
        return (
            self._file_mtime_signature(getattr(astrbot_config, "config_path", None)),
            self._file_mtime_signature(self._get_config_file_path()),
            self._payload_signature(self._plain_mapping(astrbot_config)),
            self._payload_signature(self.plugin_config.to_dict()),
        )

    def _remember_config_sync_state(
        self,
        astrbot_config: MutableMapping[str, Any],
    ) -> None:
        self._set_container_attr(
            "_config_source_sync_signature",
            self._config_source_signature(astrbot_config),
        )

    def _forget_config_sync_state(self) -> None:
        self._set_container_attr("_config_source_sync_signature", None)

    def _apply_astrbot_config_to_plugin(
        self,
        astrbot_config: MutableMapping[str, Any],
    ) -> bool:
        """Pull newer AstrBot plugin-page settings into the WebUI runtime config."""
        if not self.plugin_config:
            return False

        flat_config = self._flatten_payload(self._plain_mapping(astrbot_config))
        known_config = {
            key: value
            for key, value in flat_config.items()
            if hasattr(self.plugin_config, key)
        }
        if not known_config:
            return False
        initial_webui_password = ""
        if "webui_initial_password" in known_config:
            initial_webui_password = str(
                known_config.get("webui_initial_password") or ""
            ).strip()
            known_config["webui_initial_password"] = ""

        original_config = self.plugin_config.to_dict()
        changed_keys = [
            key
            for key, value in known_config.items()
            if original_config.get(key) != value
        ]
        if not changed_keys:
            return False

        merged_config = {**original_config, **known_config}
        try:
            validated_config = self.plugin_config.__class__.model_validate(merged_config)
        except ValidationError as e:
            logger.warning(f"同步 AstrBot 插件页配置到 WebUI 失败: {e}", exc_info=True)
            return False

        for field_name, value in validated_config.model_dump().items():
            if hasattr(self.plugin_config, field_name):
                setattr(self.plugin_config, field_name, value)

        if getattr(self.plugin_config, "data_dir", None):
            self.plugin_config.messages_db_path = os.path.join(
                self.plugin_config.data_dir, FileNames.MESSAGES_DB_FILE
            )
            self.plugin_config.learning_log_path = os.path.join(
                self.plugin_config.data_dir, FileNames.LEARNING_LOG_FILE
            )

        if (
            initial_webui_password
            and getattr(self.plugin_config, "enable_webui_password", False) is True
        ):
            strength_result = validate_password_strength(initial_webui_password)
            if strength_result["valid"]:
                password_success, password_message = AuthService(self.container).configure_password(
                    initial_webui_password,
                    must_change=False,
                )
                if not password_success:
                    logger.warning(f"AstrBot 插件页 WebUI 初始密码保存失败: {password_message}")
            else:
                issues = "、".join(strength_result["issues"]) if strength_result["issues"] else "密码强度不足"
                logger.warning(f"AstrBot 插件页 WebUI 初始密码无效: {issues}")

        self._sync_runtime_components(changed_keys)
        config_file = self._get_config_file_path()
        if not self.plugin_config.save_to_file(config_file):
            logger.warning("AstrBot 插件页配置已同步到内存，但写入 WebUI 配置文件失败")
        self._sync_astrbot_group_config(self.plugin_config, list(known_config))

        logger.info(
            "AstrBot 插件页配置已同步到 WebUI: "
            f"{', '.join(sorted(changed_keys))}"
        )
        return True

    def _sync_config_sources(self, *, force: bool = False) -> None:
        """Keep AstrBot plugin-page config and WebUI config on the same values."""
        astrbot_config = self._get_astrbot_config()
        if not astrbot_config or not self.plugin_config:
            return

        signature = self._config_source_signature(astrbot_config)
        if (
            not force
            and self._get_container_attr("_config_source_sync_signature") == signature
        ):
            return

        if self._astrbot_config_is_newer(astrbot_config):
            self._apply_astrbot_config_to_plugin(astrbot_config)
            self._remember_config_sync_state(astrbot_config)
            return

        self._sync_astrbot_group_config(
            self.plugin_config,
            list(self.plugin_config.to_dict()),
        )
        self._remember_config_sync_state(astrbot_config)

    @staticmethod
    def _field_group_index(schema_definition: Dict[str, Any]) -> Dict[str, str]:
        field_to_group: Dict[str, str] = {}
        for group_key, group_definition in schema_definition.items():
            if not isinstance(group_definition, dict):
                continue
            items = group_definition.get("items", {})
            if not isinstance(items, dict):
                continue
            for field_key in items:
                field_to_group[field_key] = group_key
        return field_to_group

    def _sync_astrbot_group_config(
        self,
        validated_config: Any,
        _submitted_keys: List[str],
    ) -> bool:
        """Pass the full WebUI config through to AstrBot's grouped plugin-page config."""
        astrbot_config = self._get_astrbot_config()
        if not astrbot_config:
            return False

        schema_definition = self._merged_schema_definition()
        current_payload = self._plain_mapping(astrbot_config)
        schema_fields = {
            field_name
            for group_definition in schema_definition.values()
            if isinstance(group_definition, dict)
            for field_name in group_definition.get("items", {})
        }
        if hasattr(validated_config, "model_dump"):
            config_values = validated_config.model_dump()
        else:
            config_values = {
                field_name: getattr(validated_config, field_name)
                for field_name in schema_fields
                if hasattr(validated_config, field_name)
            }
        config_field_names = set(config_values)
        next_payload = {
            key: value
            for key, value in current_payload.items()
            if key not in config_field_names
        }
        synced_groups = set()

        for group_key, group_definition in schema_definition.items():
            if not isinstance(group_definition, dict):
                continue
            items = group_definition.get("items", {})
            if not isinstance(items, dict):
                continue
            group = next_payload.get(group_key)
            if not isinstance(group, MutableMapping):
                group = {}
            else:
                group = dict(group)

            group_updated = False
            for field_name in items:
                if field_name not in config_values:
                    continue
                group[field_name] = config_values[field_name]
                group_updated = True

            if group_updated:
                next_payload[group_key] = group
                synced_groups.add(group_key)

        if not synced_groups:
            return False

        if self._payload_signature(current_payload) == self._payload_signature(
            next_payload
        ):
            return False

        astrbot_config.clear()
        astrbot_config.update(next_payload)

        save_config = getattr(astrbot_config, "save_config", None)
        if callable(save_config):
            try:
                save_config()
            except TypeError:
                try:
                    save_config(self._plain_mapping(astrbot_config))
                except Exception as e:
                    logger.warning(f"同步 AstrBot 插件页配置失败: {e}", exc_info=True)
                    return False
            except Exception as e:
                logger.warning(f"同步 AstrBot 插件页配置失败: {e}", exc_info=True)
                return False

        logger.info(
            "WebUI 配置已同步到 AstrBot 插件页分组: "
            f"{', '.join(sorted(synced_groups))}"
        )
        return True

    def _sync_runtime_components(self, changed_keys: List[str]) -> None:
        """Refresh runtime objects that cache values derived from PluginConfig."""
        plugin = self._get_container_attr("plugin_instance")
        if plugin is not None:
            try:
                plugin.plugin_config = self.plugin_config
            except Exception:
                logger.debug("同步 plugin.plugin_config 失败", exc_info=True)

            qq_filter = getattr(plugin, "qq_filter", None)
            if qq_filter and any(
                key in changed_keys for key in ("target_qq_list", "target_blacklist")
            ):
                try:
                    qq_filter.target_qq_list = list(self.plugin_config.target_qq_list)
                    qq_filter.blacklist = list(self.plugin_config.target_blacklist)
                except Exception:
                    logger.debug("同步 QQ 过滤器配置失败", exc_info=True)

        self._refresh_learning_runtime(getattr(plugin, "progressive_learning", None))
        self._refresh_learning_runtime(self._get_container_attr("progressive_learning"))

        self.container.plugin_config = self.plugin_config
        try:
            from ..config import WebUIConfig
            self.container.webui_config = WebUIConfig.from_plugin_config(self.plugin_config)
        except Exception:
            logger.debug("同步 WebUIConfig 失败", exc_info=True)

    def _refresh_learning_runtime(self, progressive_learning: Any) -> None:
        if not progressive_learning:
            return
        if hasattr(progressive_learning, "batch_size"):
            progressive_learning.batch_size = self.plugin_config.max_messages_per_batch
        if hasattr(progressive_learning, "learning_interval"):
            progressive_learning.learning_interval = (
                self.plugin_config.learning_interval_hours * 3600
            )
        if hasattr(progressive_learning, "quality_threshold"):
            progressive_learning.quality_threshold = self.plugin_config.style_update_threshold

    @staticmethod
    def _normalize_provider_type(provider_type: Any, default_type: str = "") -> str:
        raw_value = provider_type
        if hasattr(raw_value, "value"):
            raw_value = raw_value.value
        elif hasattr(raw_value, "name"):
            raw_value = raw_value.name
        normalized = str(raw_value or default_type or "").strip().lower()
        return _PROVIDER_TYPE_ALIASES.get(normalized, normalized)

    @staticmethod
    def _provider_type_value(provider: Any, default_type: str = "") -> str:
        try:
            meta = provider.meta()
        except Exception:
            meta = None

        raw_type = getattr(getattr(meta, "provider_type", None), "value", None)
        if not raw_type:
            raw_type = getattr(getattr(meta, "provider_type", None), "name", None)
        if not raw_type:
            raw_type = default_type
        return ConfigService._normalize_provider_type(raw_type, default_type)

    @staticmethod
    def _provider_type_label(provider_type: str) -> str:
        return _PROVIDER_TYPE_LABELS.get(provider_type, provider_type)

    @staticmethod
    def _build_provider_option(
        provider_id: Any,
        model_name: Any = None,
        provider_type: str = "",
    ) -> Optional[Dict[str, str]]:
        if not provider_id:
            return None

        label_parts = [str(provider_id)]
        if model_name and str(model_name) not in str(provider_id):
            label_parts.append(str(model_name))
        if provider_type:
            label_parts.append(provider_type)

        return {
            "value": str(provider_id),
            "label": " / ".join(label_parts),
            "provider_type": provider_type,
            "provider_type_label": ConfigService._provider_type_label(provider_type),
        }

    @staticmethod
    def _provider_option(provider: Any, default_type: str = "") -> Optional[Dict[str, str]]:
        try:
            meta = provider.meta()
        except Exception:
            meta = None

        provider_id = getattr(meta, "id", None) or getattr(provider, "id", None)
        provider_type = ConfigService._provider_type_value(provider, default_type)
        model_name = getattr(meta, "model", None) or getattr(provider, "model", None)
        return ConfigService._build_provider_option(provider_id, model_name, provider_type)

    @staticmethod
    def _provider_option_from_config(
        provider_config: Any,
        provider_source_types: Dict[str, str],
        default_type: str = "",
    ) -> Optional[Dict[str, str]]:
        if not isinstance(provider_config, dict):
            return None

        provider_id = provider_config.get("id") or provider_config.get("provider_id")
        if not provider_id:
            return None

        provider_source_id = provider_config.get("provider_source_id")
        provider_type = provider_config.get("provider_type")
        if not provider_type and provider_source_id:
            provider_type = provider_source_types.get(str(provider_source_id))
        provider_type = ConfigService._normalize_provider_type(provider_type, default_type)

        model_name = (
            provider_config.get("model")
            or provider_config.get("embedding_model")
            or provider_config.get("rerank_model")
        )
        return ConfigService._build_provider_option(provider_id, model_name, provider_type)

    @staticmethod
    def _dedupe_options(options: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        result: List[Dict[str, str]] = []
        for option in options:
            value = option.get("value")
            provider_type = option.get("provider_type", "")
            key = (value, provider_type)
            if not value or key in seen:
                continue
            seen.add(key)
            result.append(option)
        return result

    @staticmethod
    def _as_provider_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, (str, bytes, dict)):
            return []
        try:
            return list(value)
        except TypeError:
            return []

    def _get_provider_context(self):
        factory_manager = getattr(self.container, "factory_manager", None)
        if not factory_manager or not hasattr(factory_manager, "get_service_factory"):
            return None
        service_factory = factory_manager.get_service_factory()
        return getattr(service_factory, "context", None)

    @staticmethod
    def _provider_source_types(provider_manager: Any) -> Dict[str, str]:
        source_types: Dict[str, str] = {}
        for provider_source in ConfigService._as_provider_list(
            getattr(provider_manager, "provider_sources_config", None)
        ):
            if not isinstance(provider_source, dict):
                continue
            source_id = provider_source.get("id")
            if not source_id:
                continue
            source_types[str(source_id)] = ConfigService._normalize_provider_type(
                provider_source.get("provider_type"),
                "chat_completion",
            )
        return source_types

    def _provider_options(self, expected_type: Optional[str] = None) -> List[Dict[str, str]]:
        factory_manager = getattr(self.container, "factory_manager", None)
        if not factory_manager or not hasattr(factory_manager, "get_service_factory"):
            return []

        try:
            context = self._get_provider_context()
            if not context:
                return []

            options: List[Dict[str, str]] = []
            expected = self._normalize_provider_type(expected_type)
            provider_manager = getattr(context, "provider_manager", None)

            if expected in {"", "chat_completion", "llm", "chat"} and callable(getattr(context, "get_all_providers", None)):
                for provider in self._as_provider_list(context.get_all_providers()):
                    option = self._provider_option(provider, "chat_completion")
                    if option:
                        options.append(option)
            if expected in {"", "chat_completion"} and provider_manager and hasattr(provider_manager, "provider_insts"):
                for provider in self._as_provider_list(provider_manager.provider_insts):
                    option = self._provider_option(provider, "chat_completion")
                    if option:
                        options.append(option)

            if expected in {"", "embedding"} and callable(getattr(context, "get_all_embedding_providers", None)):
                for provider in self._as_provider_list(context.get_all_embedding_providers()):
                    option = self._provider_option(provider, "embedding")
                    if option:
                        options.append(option)
            if expected in {"", "embedding"} and provider_manager and hasattr(provider_manager, "embedding_provider_insts"):
                for provider in self._as_provider_list(provider_manager.embedding_provider_insts):
                    option = self._provider_option(provider, "embedding")
                    if option:
                        options.append(option)

            if expected in {"", "rerank", "reranker"}:
                rerank_providers = []
                rerank_getter = getattr(context, "get_all_rerank_providers", None)
                if callable(rerank_getter):
                    rerank_providers = self._as_provider_list(rerank_getter())
                if not rerank_providers and provider_manager and hasattr(provider_manager, "rerank_provider_insts"):
                    rerank_providers = provider_manager.rerank_provider_insts
                for provider in self._as_provider_list(rerank_providers):
                    option = self._provider_option(provider, "rerank")
                    if option:
                        options.append(option)

            if expected == "" and provider_manager and hasattr(provider_manager, "inst_map"):
                for provider in provider_manager.inst_map.values():
                    option = self._provider_option(provider)
                    if option:
                        options.append(option)

            if provider_manager and hasattr(provider_manager, "providers_config"):
                provider_source_types = self._provider_source_types(provider_manager)
                for provider_config in self._as_provider_list(provider_manager.providers_config):
                    option = self._provider_option_from_config(provider_config, provider_source_types)
                    if not option:
                        continue
                    option_type = option.get("provider_type", "")
                    if expected and option_type != expected:
                        continue
                    options.append(option)

            return self._dedupe_options(options)
        except Exception as e:
            logger.warning(f"获取 Provider 列表失败: {e}")
            return []

    @staticmethod
    def _provider_expected_type_for_field(key: str) -> Optional[str]:
        if key in {"filter_provider_id", "refine_provider_id", "reinforce_provider_id"}:
            return "chat_completion"
        if key == "embedding_provider_id":
            return "embedding"
        if key == "rerank_provider_id":
            return "rerank"
        return None

    def _build_field_spec(
        self,
        key: str,
        raw_spec: Dict[str, Any],
        current_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        field_type = raw_spec.get("type", "string")
        widget = "text"
        if raw_spec.get("_readonly"):
            widget = "readonly"
        elif raw_spec.get("_secret"):
            widget = "password"
        elif raw_spec.get("_special") == "select_provider" or key.endswith("_provider_id"):
            widget = "provider"
        elif key in _ENUM_FIELD_OPTIONS:
            widget = "select"
        elif field_type == "bool":
            widget = "toggle"
        elif field_type in {"int", "float"}:
            widget = "number"
        elif field_type == "list":
            widget = "textarea"

        default_value = raw_spec.get("default")
        value = current_config.get(key, default_value)
        if field_type == "list" and value is None:
            value = []

        field_spec = {
            "key": key,
            "label": raw_spec.get("description", key),
            "hint": raw_spec.get("hint", ""),
            "type": field_type,
            "widget": widget,
            "default": default_value,
            "value": value,
            "editable": not raw_spec.get("_readonly", False),
            "secret": bool(raw_spec.get("_secret")),
            "nullable": default_value is None or raw_spec.get("_nullable", False) or key.endswith("_provider_id"),
            "restart_required": key in _RESTART_REQUIRED_KEYS,
        }
        if raw_spec.get("_secret"):
            field_spec["value"] = ""

        if field_type == "list":
            items_spec = raw_spec.get("items", {})
            if isinstance(items_spec, dict):
                field_spec["item_type"] = items_spec.get("type", "string")
            else:
                field_spec["item_type"] = "string"

        options = raw_spec.get("options")
        if key in _ENUM_FIELD_OPTIONS:
            options = _ENUM_FIELD_OPTIONS[key]
        if options:
            field_spec["options"] = options

        if field_spec["widget"] == "provider":
            field_spec["provider_type"] = (
                self._provider_expected_type_for_field(key)
                or self._normalize_provider_type(raw_spec.get("_provider_type"))
                or ""
            )
            field_spec["provider_type_label"] = _PROVIDER_TYPE_LABELS.get(
                field_spec["provider_type"],
                field_spec["provider_type"] or "Provider",
            )
            field_spec["options"] = self._provider_options(field_spec["provider_type"])

        return field_spec

    def _build_group_schema(self, schema_definition: Dict[str, Any]) -> List[Dict[str, Any]]:
        current_config = self.plugin_config.to_dict() if self.plugin_config else {}
        groups: List[Dict[str, Any]] = []

        for group_key, group_definition in schema_definition.items():
            if not isinstance(group_definition, dict):
                continue
            items = group_definition.get("items", {})
            if not isinstance(items, dict):
                continue

            fields = [
                self._build_field_spec(field_key, field_spec, current_config)
                for field_key, field_spec in items.items()
            ]

            groups.append(
                {
                    "key": group_key,
                    "title": group_definition.get("description", group_key),
                    "hint": group_definition.get("hint", ""),
                    "fields": fields,
                }
            )

        return groups

    def _collect_extra_schema(self) -> Dict[str, Any]:
        return _EXTRA_SCHEMA_DEFINITION

    def _merge_schema_definitions(
        self,
        base_schema: Dict[str, Any],
        extra_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {
            key: dict(value) if isinstance(value, dict) else value
            for key, value in base_schema.items()
        }

        for group_key, group_definition in extra_schema.items():
            if (
                group_key in merged
                and isinstance(merged[group_key], dict)
                and isinstance(group_definition, dict)
            ):
                current_group = dict(merged[group_key])
                for key, value in group_definition.items():
                    if key == "items" and isinstance(value, dict):
                        current_items = current_group.get("items", {})
                        if not isinstance(current_items, dict):
                            current_items = {}
                        current_group["items"] = {**current_items, **value}
                    else:
                        current_group[key] = value
                merged[group_key] = current_group
            else:
                merged[group_key] = group_definition

        return merged

    async def get_config(self) -> Dict[str, Any]:
        """
        获取插件配置

        Returns:
            Dict: 插件配置字典
        """
        if self.plugin_config:
            self._sync_config_sources()
            return self.plugin_config.to_dict()
        raise ValueError("Plugin config not initialized")

    async def get_config_schema(self) -> Dict[str, Any]:
        """获取 dashboard 全量设置所需的 schema 和当前值。"""
        if not self.plugin_config:
            raise ValueError("Plugin config not initialized")

        self._sync_config_sources()
        merged_schema = self._merged_schema_definition()

        return {
            "config": self.plugin_config.to_dict(),
            "groups": self._build_group_schema(merged_schema),
            "provider_options": self._provider_options(),
            "provider_options_by_type": {
                "chat_completion": self._provider_options("chat_completion"),
                "embedding": self._provider_options("embedding"),
                "rerank": self._provider_options("rerank"),
            },
        }

    async def update_config(self, new_config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        更新插件配置

        Args:
            new_config: 新的配置数据

        Returns:
            Tuple[bool, str, Dict]: (是否成功, 消息, 更新后的配置)
        """
        if not self.plugin_config:
            raise ValueError("Plugin config not initialized")

        payload = new_config or {}
        if isinstance(payload, dict):
            for wrapper_key in ("config", "new_config", "settings", "data"):
                wrapped = payload.get(wrapper_key)
                if isinstance(wrapped, dict):
                    payload = wrapped
                    break

        flat_config = self._flatten_payload(payload if isinstance(payload, dict) else {})
        initial_webui_password = ""
        if "webui_initial_password" in flat_config:
            initial_webui_password = str(flat_config.get("webui_initial_password") or "").strip()
            flat_config["webui_initial_password"] = ""

        original_config = self.plugin_config.to_dict()
        merged_config = dict(original_config)
        changed_keys: List[str] = []

        for key, value in flat_config.items():
            if hasattr(self.plugin_config, key):
                merged_config[key] = value
                if original_config.get(key) != value:
                    changed_keys.append(key)
            else:
                logger.warning(f"配置项 {key} 不存在，跳过")

        try:
            validated_config = self.plugin_config.__class__.model_validate(merged_config)
        except ValidationError as e:
            logger.error(f"配置校验失败: {e}", exc_info=True)
            return False, f"配置校验失败: {str(e)}", original_config

        validation_messages = validated_config.validate_config()
        blocking_errors = [msg for msg in validation_messages if not msg.startswith(" ")]
        warnings = [msg.strip() for msg in validation_messages if msg.startswith(" ")]

        provider_error = "至少需要配置一个模型提供商ID"
        non_provider_errors = [msg for msg in blocking_errors if provider_error not in msg]
        if non_provider_errors:
            return False, "；".join(non_provider_errors), original_config

        if provider_error in "；".join(blocking_errors):
            warnings.append("至少需要配置一个模型提供商ID，系统将继续依赖 AstrBot 的自动兜底 Provider 选择")

        auth_service = AuthService(self.container)
        password_enabled = getattr(validated_config, "enable_webui_password", False) is True
        if initial_webui_password and not password_enabled:
            return False, "设置 WebUI 初始密码前请先启用 WebUI 登录密码", original_config

        if initial_webui_password:
            strength_result = validate_password_strength(initial_webui_password)
            if not strength_result["valid"]:
                issues = "、".join(strength_result["issues"]) if strength_result["issues"] else "密码强度不足"
                return False, issues, original_config

        if (
            password_enabled
            and not initial_webui_password
            and not auth_service.has_password_config()
            and not os.getenv(INITIAL_WEBUI_PASSWORD_ENV_VAR, "").strip()
        ):
            return False, (
                "开启 WebUI 登录密码前，请填写 WebUI 一次性初始密码，"
                f"或设置环境变量 {INITIAL_WEBUI_PASSWORD_ENV_VAR}"
            ), original_config

        for field_name, value in validated_config.model_dump().items():
            if hasattr(self.plugin_config, field_name):
                setattr(self.plugin_config, field_name, value)

        if "log_level" in changed_keys or "debug_mode" in changed_keys:
            applied_level = apply_astrbot_log_level(
                getattr(self.plugin_config, "log_level", "info"),
                debug_mode=getattr(self.plugin_config, "debug_mode", False),
                fallback="info",
            )
            self.plugin_config.log_level = applied_level
            logger.info(f"AstrBot 日志等级已更新为: {applied_level}")

        if getattr(self.plugin_config, "data_dir", None):
            self.plugin_config.messages_db_path = os.path.join(
                self.plugin_config.data_dir, FileNames.MESSAGES_DB_FILE
            )
            self.plugin_config.learning_log_path = os.path.join(
                self.plugin_config.data_dir, FileNames.LEARNING_LOG_FILE
            )

        if initial_webui_password:
            password_success, password_message = AuthService(self.container).configure_password(
                initial_webui_password,
                must_change=False,
            )
            if not password_success:
                return False, password_message, original_config

        self._sync_runtime_components(changed_keys)
        astrbot_config_synced = self._sync_astrbot_group_config(
            self.plugin_config,
            list(flat_config),
        )

        llm_adapter = getattr(self.container, "llm_adapter", None)
        if llm_adapter and hasattr(llm_adapter, "initialize_providers"):
            try:
                llm_adapter.initialize_providers(self.plugin_config)
            except Exception as e:
                logger.warning(f"重新初始化 LLM Provider 失败: {e}", exc_info=True)

        config_file = self._get_config_file_path()
        if not self.plugin_config.save_to_file(config_file):
            return False, "配置已更新到内存，但持久化到文件失败", self.plugin_config.to_dict()
        astrbot_config = self._get_astrbot_config()
        if astrbot_config:
            self._remember_config_sync_state(astrbot_config)
        else:
            self._forget_config_sync_state()

        if changed_keys:
            logger.info(f"配置已更新: {', '.join(changed_keys)}")

        message = "Config updated successfully"
        if warnings:
            message = f"{message}，{'; '.join(warnings)}"
        if astrbot_config_synced:
            message = f"{message}；已同步到插件设置页"
        if any(key in _RESTART_REQUIRED_KEYS for key in changed_keys):
            message = f"{message}；部分变更重启后生效"

        return True, message, self.plugin_config.to_dict()
