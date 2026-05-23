"""
配置服务 - 处理插件配置相关业务逻辑
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from astrbot.api import logger

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
        {"value": "sqlite", "label": "SQLite"},
        {"value": "mysql", "label": "MySQL"},
        {"value": "postgresql", "label": "PostgreSQL"},
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

    def _get_config_file_path(self) -> str:
        data_dir = getattr(self.plugin_config, "data_dir", None) if self.plugin_config else None
        if isinstance(data_dir, (str, os.PathLike)) and os.fspath(data_dir):
            return os.path.join(os.fspath(data_dir), FileNames.CONFIG_FILE)
        try:
            from ...config import DEFAULT_DATA_DIR
        except ImportError:
            from config import DEFAULT_DATA_DIR
        return os.path.join(DEFAULT_DATA_DIR, FileNames.CONFIG_FILE)

    def _flatten_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flat: Dict[str, Any] = {}

        for key, value in payload.items():
            if isinstance(value, dict):
                flat.update(self._flatten_payload(value))
            else:
                flat[key] = value

        return flat

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
            "nullable": default_value is None or raw_spec.get("_nullable", False) or key.endswith("_provider_id"),
            "restart_required": key in _RESTART_REQUIRED_KEYS,
        }

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
            return self.plugin_config.to_dict()
        raise ValueError("Plugin config not initialized")

    async def get_config_schema(self) -> Dict[str, Any]:
        """获取 dashboard 全量设置所需的 schema 和当前值。"""
        if not self.plugin_config:
            raise ValueError("Plugin config not initialized")

        base_schema = _load_schema_definition()
        merged_schema = self._merge_schema_definitions(
            base_schema,
            self._collect_extra_schema(),
        )

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
        except Exception as e:
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

        llm_adapter = getattr(self.container, "llm_adapter", None)
        if llm_adapter and hasattr(llm_adapter, "initialize_providers"):
            try:
                llm_adapter.initialize_providers(self.plugin_config)
            except Exception as e:
                logger.warning(f"重新初始化 LLM Provider 失败: {e}", exc_info=True)

        config_file = self._get_config_file_path()
        if not self.plugin_config.save_to_file(config_file):
            return False, "配置已更新到内存，但持久化到文件失败", self.plugin_config.to_dict()

        if changed_keys:
            logger.info(f"配置已更新: {', '.join(changed_keys)}")

        message = "Config updated successfully"
        if warnings:
            message = f"{message}，{'; '.join(warnings)}"
        if any(key in _RESTART_REQUIRED_KEYS for key in changed_keys):
            message = f"{message}；部分变更重启后生效"

        return True, message, self.plugin_config.to_dict()
