"""AstrBot official Plugin Page API adapter.

This module registers lightweight APIs for AstrBot's embedded plugin pages.
It intentionally reuses the existing runtime/WebUI service container instead
of proxying to the standalone WebUI server.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from astrbot.api import logger

PLUGIN_NAME = "astrbot_plugin_self_learning"
PAGE_API_PREFIX = f"/{PLUGIN_NAME}/page"


class PluginPageApi:
    """Official AstrBot Plugin Page API for self-learning dashboard."""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    def register_routes(self) -> None:
        """Register routes consumed by ``pages/dashboard``."""
        register = self.plugin.context.register_web_api
        register(
            f"{PAGE_API_PREFIX}/overview",
            self.get_overview,
            ["GET"],
            "Self Learning embedded dashboard overview",
        )

    async def get_overview(self) -> dict[str, Any]:
        """Return a compact, fault-tolerant dashboard snapshot."""
        try:
            from ..webui.dependencies import get_container
            from ..webui.services.jargon_service import JargonService
            from ..webui.services.learning_service import LearningService
            from ..webui.services.metrics_service import MetricsService
            from ..webui.services.persona_backup_service import PersonaBackupService
            from ..webui.services.persona_service import PersonaService
        except ImportError:
            from webui.dependencies import get_container
            from webui.services.jargon_service import JargonService
            from webui.services.learning_service import LearningService
            from webui.services.metrics_service import MetricsService
            from webui.services.persona_backup_service import PersonaBackupService
            from webui.services.persona_service import PersonaService

        container = get_container()
        errors: dict[str, str] = {}

        plugin_config = getattr(self.plugin, "plugin_config", None)
        webui_config = getattr(container, "webui_config", None)
        db_manager = getattr(container, "database_manager", None) or getattr(
            self.plugin, "db_manager", None
        )

        learning_stats = self._serialize_learning_stats(
            getattr(self.plugin, "learning_stats", None)
        )

        jargon_stats = await self._safe_section(
            "jargon",
            lambda: JargonService(container).get_jargon_stats(),
            errors,
            default={
                "total_candidates": 0,
                "confirmed_jargon": 0,
                "completed_inference": 0,
                "total_occurrences": 0,
                "average_count": 0,
                "active_groups": 0,
            },
        )
        style_results = await self._safe_section(
            "style",
            lambda: LearningService(container).get_style_learning_results(),
            errors,
            default={"statistics": {}, "style_progress": []},
        )
        persona_state = await self._safe_section(
            "persona",
            lambda: PersonaService(container).get_current_persona_state("default"),
            errors,
            default={
                "group_id": "default",
                "persona": {"persona_id": "default", "name": "默认人格"},
                "prompt_length": 0,
                "begin_dialog_count": 0,
                "tool_count": 0,
                "degraded": True,
            },
        )
        backups = await self._safe_section(
            "persona_backups",
            lambda: PersonaBackupService(container).list_backups(limit=8),
            errors,
            default={"backups": [], "total": 0, "available": False},
        )
        metrics = await self._safe_section(
            "metrics",
            lambda: MetricsService(container).get_intelligence_metrics("default"),
            errors,
            default={"overall_score": 0, "dimensions": {}, "trends": []},
        )

        style_stats = style_results.get("statistics") if isinstance(style_results, dict) else {}
        style_stats = style_stats if isinstance(style_stats, dict) else {}

        modules = self._build_modules(
            plugin_config=plugin_config,
            jargon_stats=jargon_stats,
            style_stats=style_stats,
            persona_state=persona_state,
            backups=backups,
            metrics=metrics,
        )

        return self._ok(
            {
                "plugin": {
                    "name": PLUGIN_NAME,
                    "display_name": "Self Learning",
                    "version": self._config_value(plugin_config, "version", "3.2.0"),
                    "generated_at": datetime.now().isoformat(),
                },
                "runtime": {
                    "database_ready": bool(db_manager),
                    "database_degraded": bool(
                        getattr(container, "database_degraded", False)
                    ),
                    "database_error": getattr(container, "database_start_error", None),
                    "services": {
                        "plugin_config": bool(plugin_config),
                        "webui_config": bool(webui_config),
                        "database_manager": bool(db_manager),
                        "persona_manager": bool(getattr(container, "persona_manager", None)),
                        "persona_web_manager": bool(
                            getattr(container, "persona_web_manager", None)
                        ),
                        "intelligence_metrics": bool(
                            getattr(container, "intelligence_metrics_service", None)
                        ),
                    },
                },
                "webui": self._build_webui_snapshot(plugin_config, webui_config),
                "learning_stats": learning_stats,
                "jargon": jargon_stats,
                "style": style_results,
                "persona": persona_state,
                "persona_backups": backups,
                "metrics": metrics,
                "modules": modules,
                "quick_links": self._build_quick_links(plugin_config, webui_config),
                "errors": errors,
            }
        )

    @staticmethod
    async def _safe_section(
        name: str,
        loader: Callable[[], Awaitable[dict[str, Any]]],
        errors: dict[str, str],
        *,
        default: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            data = await loader()
            return data if isinstance(data, dict) else default
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] {name} section unavailable: {exc}", exc_info=True)
            errors[name] = str(exc)
            return default

    @staticmethod
    def _serialize_learning_stats(stats: Any) -> dict[str, Any]:
        if stats is None:
            return {
                "total_messages_collected": 0,
                "filtered_messages": 0,
                "style_updates": 0,
                "persona_updates": 0,
                "last_learning_time": None,
                "last_persona_update": None,
            }
        if is_dataclass(stats):
            return asdict(stats)
        return {
            "total_messages_collected": int(
                getattr(stats, "total_messages_collected", 0) or 0
            ),
            "filtered_messages": int(getattr(stats, "filtered_messages", 0) or 0),
            "style_updates": int(getattr(stats, "style_updates", 0) or 0),
            "persona_updates": int(getattr(stats, "persona_updates", 0) or 0),
            "last_learning_time": getattr(stats, "last_learning_time", None),
            "last_persona_update": getattr(stats, "last_persona_update", None),
        }

    @classmethod
    def _build_modules(
        cls,
        *,
        plugin_config: Any,
        jargon_stats: dict[str, Any],
        style_stats: dict[str, Any],
        persona_state: dict[str, Any],
        backups: dict[str, Any],
        metrics: dict[str, Any],
    ) -> list[dict[str, Any]]:
        confirmed_jargon = cls._as_int(jargon_stats.get("confirmed_jargon"))
        unique_styles = cls._as_int(style_stats.get("unique_styles"))
        persona_prompt_len = cls._as_int(persona_state.get("prompt_length"))
        backup_total = cls._as_int(backups.get("total"))
        intelligence_score = cls._as_number(metrics.get("overall_score"))

        return [
            {
                "id": "jargon",
                "title": "黑话学习",
                "description": "群内专属词、梗和语义推断",
                "enabled": cls._config_bool(plugin_config, "enable_jargon_learning", True),
                "metric": confirmed_jargon,
                "metric_label": "已确认黑话",
                "accent": "#14b8a6",
                "target": "jargon",
            },
            {
                "id": "style",
                "title": "表达方式学习",
                "description": "语气、句式、few-shot 与表达模式",
                "enabled": cls._config_bool(plugin_config, "enable_style_learning", True),
                "metric": unique_styles,
                "metric_label": "风格样本",
                "accent": "#4f46e5",
                "target": "style",
            },
            {
                "id": "persona",
                "title": "人格学习",
                "description": "人格演化、更新审查与备份恢复",
                "enabled": cls._config_bool(
                    plugin_config, "enable_persona_evolution", True
                ),
                "metric": persona_prompt_len,
                "metric_label": "人格提示词字数",
                "accent": "#f59e0b",
                "target": "persona",
            },
            {
                "id": "reviews",
                "title": "审查队列",
                "description": "学习结果进入人格前的确认区",
                "enabled": True,
                "metric": backup_total,
                "metric_label": "近期人格备份",
                "accent": "#e11d48",
                "target": "reviews",
            },
            {
                "id": "metrics",
                "title": "智能指标",
                "description": "回复多样性、好感度与智能评分",
                "enabled": True,
                "metric": round(intelligence_score, 2),
                "metric_label": "综合评分",
                "accent": "#0ea5e9",
                "target": "metrics",
            },
        ]

    @staticmethod
    def _build_webui_snapshot(plugin_config: Any, webui_config: Any) -> dict[str, Any]:
        enabled = PluginPageApi._config_bool(
            plugin_config, "enable_web_interface", True
        )
        host = getattr(webui_config, "host", None) or PluginPageApi._config_value(
            plugin_config, "web_interface_host", "127.0.0.1"
        )
        port = getattr(webui_config, "port", None) or PluginPageApi._config_value(
            plugin_config, "web_interface_port", 7833
        )
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 7833
        display_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::"} else str(host)
        return {
            "enabled": enabled,
            "host": host,
            "port": port,
            "dashboard_url": f"http://{display_host}:{port}",
        }

    @staticmethod
    def _build_quick_links(plugin_config: Any, webui_config: Any) -> list[dict[str, str]]:
        webui = PluginPageApi._build_webui_snapshot(plugin_config, webui_config)
        return [
            {
                "id": "full_dashboard",
                "label": "完整 WebUI",
                "url": webui["dashboard_url"],
                "description": "打开 7833 独立管理界面",
            },
            {
                "id": "plugin_settings",
                "label": "插件设置",
                "url": "#/extension",
                "description": "回到 AstrBot 插件管理",
            },
        ]

    @staticmethod
    def _config_value(config: Any, name: str, default: Any = None) -> Any:
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(name, default)
        return getattr(config, name, default)

    @staticmethod
    def _config_bool(config: Any, name: str, default: bool = False) -> bool:
        value = PluginPageApi._config_value(config, name, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _as_number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _ok(data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "data": data}
