"""Integration status service for companion plugin dashboards."""

from __future__ import annotations

from typing import Any, Dict, Optional

LIVINGMEMORY_PAGE_API_BASE = "/astrbot_plugin_livingmemory/page"
LIVINGMEMORY_PAGE_CONTENT = "/api/plugin/page/content/astrbot_plugin_livingmemory/dashboard/"

SELF_LEARNING_API_ENDPOINTS = [
    "GET /api/integrations/status",
    "GET /api/config/schema",
    "POST /api/config",
    "GET /api/metrics",
    "GET /api/graphs/memory",
    "GET /api/graphs/knowledge",
    "GET /api/persona_updates",
    "GET /api/jargon/list",
    "GET /api/style_learning/content_text",
]

LIVINGMEMORY_API_ENDPOINTS = [
    f"GET {LIVINGMEMORY_PAGE_API_BASE}/stats",
    f"GET {LIVINGMEMORY_PAGE_API_BASE}/memories",
    f"POST {LIVINGMEMORY_PAGE_API_BASE}/memories/update",
    f"POST {LIVINGMEMORY_PAGE_API_BASE}/memories/batch-delete",
    f"POST {LIVINGMEMORY_PAGE_API_BASE}/recall/test",
    f"GET {LIVINGMEMORY_PAGE_API_BASE}/graph/overview",
    f"POST {LIVINGMEMORY_PAGE_API_BASE}/graph/query",
]

GROUP_CHAT_PLUS_API_ENDPOINTS = [
    "POST /api/auth/login",
    "GET /api/auth/status",
    "GET /api/config",
    "PUT /api/config",
    "POST /api/config/reload",
    "GET /api/data/overview",
    "GET /api/data/status",
    "GET /api/session/list",
    "POST /api/session/clean-ghosts",
    "GET /api/security/access-log",
]


def _safe_get(mapping: Any, key: str, default: Any = None) -> Any:
    if isinstance(mapping, dict):
        return mapping.get(key, default)
    getter = getattr(mapping, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            return default
    return getattr(mapping, key, default)


def _local_host(host: Any) -> str:
    normalized = str(host or "127.0.0.1").strip() or "127.0.0.1"
    if normalized in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return normalized


def _http_url(host: Any, port: Any) -> Optional[str]:
    if port in (None, ""):
        return None
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        return None
    return f"http://{_local_host(host)}:{port_int}"


class IntegrationService:
    """Build a small runtime map of delegated capabilities and dashboards."""

    def __init__(self, container: Any) -> None:
        self.container = container

    def get_status(self) -> Dict[str, Any]:
        config = getattr(self.container, "plugin_config", None)
        delegation = self._delegation()
        status = delegation.status() if delegation else {
            "memory_delegated": False,
            "memory_plugin": None,
            "reply_delegated": False,
            "reply_plugin": None,
        }

        memory_star = delegation.memory_plugin() if delegation else None
        reply_star = delegation.reply_plugin() if delegation else None

        return {
            "delegation": status,
            "settings": self._settings(config),
            "dashboards": [
                self._self_learning_dashboard(),
                self._livingmemory_dashboard(memory_star, status),
                self._group_chat_plus_dashboard(reply_star, status),
            ],
        }

    def _delegation(self) -> Optional[Any]:
        delegation = getattr(self.container, "feature_delegation", None)
        if delegation:
            return delegation

        config = getattr(self.container, "plugin_config", None)
        factory_manager = getattr(self.container, "factory_manager", None)
        if not config or not factory_manager:
            return None

        try:
            service_factory = factory_manager.get_service_factory()
            context = getattr(service_factory, "context", None)
            if not context:
                return None
            from ...core.feature_delegation import FeatureDelegation

            delegation = FeatureDelegation(config, context)
            self.container.feature_delegation = delegation
            return delegation
        except Exception:
            return None

    @staticmethod
    def _settings(config: Any) -> Dict[str, Any]:
        keys = (
            "delegate_memory_to_livingmemory",
            "livingmemory_plugin_name",
            "disable_local_memory_when_delegated",
            "delegate_reply_to_group_chat_plus",
            "group_chat_plus_plugin_name",
            "disable_local_reply_when_delegated",
        )
        return {key: getattr(config, key, None) for key in keys}

    def _self_learning_dashboard(self) -> Dict[str, Any]:
        webui_config = getattr(self.container, "webui_config", None)
        host = getattr(webui_config, "host", "127.0.0.1")
        port = getattr(webui_config, "port", None)
        return {
            "id": "self_learning",
            "title": "Self Learning",
            "role": "学习、审查与上下文注入",
            "active": True,
            "delegated": None,
            "plugin": {
                "name": "self-learning",
                "display_name": "Self Learning",
            },
            "dashboard": {
                "available": True,
                "url": "/api/",
                "external_url": _http_url(host, port),
                "label": "本插件监控板",
                "kind": "local",
            },
            "dev_api": {
                "base": "/api",
                "mode": "quart",
                "endpoints": SELF_LEARNING_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    def _livingmemory_dashboard(self, star: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(star, "star_cls", None)
        webui_settings = {}
        config_manager = getattr(plugin, "config_manager", None)
        if config_manager:
            webui_settings = getattr(config_manager, "webui_settings", None) or {}

        dashboard_url = None
        if _safe_get(webui_settings, "enabled", False):
            dashboard_url = _http_url(
                _safe_get(webui_settings, "host", "127.0.0.1"),
                _safe_get(webui_settings, "port", 8888),
            )

        return {
            "id": "livingmemory",
            "title": "LivingMemory",
            "role": "长期记忆与图谱",
            "active": star is not None,
            "delegated": bool(status.get("memory_delegated")),
            "plugin": self._star_info(star),
            "dashboard": {
                "available": bool(dashboard_url or plugin),
                "url": dashboard_url,
                "official_page_url": LIVINGMEMORY_PAGE_CONTENT if plugin else None,
                "label": "LivingMemory 面板" if dashboard_url else "AstrBot 插件页",
                "kind": "external" if dashboard_url else "astrbot_page",
                "astrbot_page": "插件 -> LivingMemory -> Pages -> dashboard",
            },
            "dev_api": {
                "base": LIVINGMEMORY_PAGE_API_BASE,
                "mode": "astrbot_register_web_api",
                "endpoints": LIVINGMEMORY_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    def _group_chat_plus_dashboard(self, star: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(star, "star_cls", None)
        host = getattr(plugin, "web_panel_host", None)
        port = getattr(plugin, "web_panel_port", None)
        enabled = bool(getattr(plugin, "enable_web_panel", False))
        dashboard_url = _http_url(host, port) if enabled else None

        return {
            "id": "group_chat_plus",
            "title": "Group Chat Plus",
            "role": "回复决策与生成",
            "active": star is not None,
            "delegated": bool(status.get("reply_delegated")),
            "plugin": self._star_info(star),
            "dashboard": {
                "available": bool(dashboard_url),
                "url": dashboard_url,
                "label": "Group Chat Plus 面板",
                "kind": "external",
            },
            "dev_api": {
                "base": f"{dashboard_url}/api" if dashboard_url else "/api",
                "mode": "aiohttp_web_panel",
                "endpoints": GROUP_CHAT_PLUS_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    @staticmethod
    def _star_info(star: Any) -> Dict[str, Any]:
        if not star:
            return {
                "name": None,
                "display_name": None,
                "root_dir_name": None,
                "module_path": None,
            }
        return {
            "name": getattr(star, "name", None),
            "display_name": getattr(star, "display_name", None),
            "root_dir_name": getattr(star, "root_dir_name", None),
            "module_path": getattr(star, "module_path", None),
        }
