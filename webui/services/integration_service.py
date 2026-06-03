"""Integration status service for companion plugin dashboards."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import quote

LIVINGMEMORY_PAGE_API_BASE = "/astrbot_plugin_livingmemory/page"
LIVINGMEMORY_PAGE_NAME = "dashboard"
LIVINGMEMORY_EMBED_URL = "/api/integrations/embed/livingmemory"
GROUP_CHAT_PLUS_EMBED_URL = "/api/integrations/embed/group_chat_plus"
LIVINGMEMORY_PLUGIN_ALIASES = {"livingmemory", "astrbot_plugin_livingmemory"}

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


def _base_url(scheme: str, host: Any, port: Any) -> Optional[str]:
    if port in (None, ""):
        return None
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        return None
    return f"{scheme}://{_local_host(host)}:{port_int}"


def _join_url(base_url: Optional[str], path: str) -> Optional[str]:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return None


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _plugin_page_content_path(
    plugin_name: Any,
    page_name: str,
    asset_path: str = "",
) -> Optional[str]:
    name = str(plugin_name or "").strip()
    page = str(page_name or "").strip()
    if not name or not page or "/" in page or "\\" in page or page.startswith("."):
        return None
    encoded_name = quote(name, safe="")
    encoded_page = quote(page, safe="")
    path = f"/api/plugin/page/content/{encoded_name}/{encoded_page}/"

    normalized_asset = str(asset_path or "").replace("\\", "/").strip("/")
    if not normalized_asset:
        return path
    asset_parts = [part for part in normalized_asset.split("/") if part]
    if any(part in {".", ".."} for part in asset_parts):
        return None
    return f"{path}{'/'.join(quote(part, safe='') for part in asset_parts)}"


def _plugin_page_content_url(
    base_url: Optional[str],
    plugin_name: Any,
    page_name: str,
    asset_path: str = "",
) -> Optional[str]:
    path = _plugin_page_content_path(plugin_name, page_name, asset_path)
    return _join_url(base_url, path) if path else None


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

    def get_embed_target(self, plugin_id: str) -> Dict[str, Any]:
        """Return the concrete iframe target for a companion dashboard shell."""
        canonical_id = {
            "astrbot_plugin_livingmemory": "livingmemory",
            "memory": "livingmemory",
            "graphs": "livingmemory",
            "reply": "group_chat_plus",
            "reply-strategy": "group_chat_plus",
            "reply_strategy": "group_chat_plus",
            "astrbot_plugin_group_chat_plus": "group_chat_plus",
        }.get(plugin_id, plugin_id)

        payload = self.get_status()
        dashboards = {
            item.get("id"): item
            for item in payload.get("dashboards", [])
            if isinstance(item, dict)
        }
        item = dashboards.get(canonical_id)
        if not item:
            return {
                "id": canonical_id,
                "title": plugin_id,
                "role": "",
                "available": False,
                "target_url": None,
                "external_url": None,
                "official_page_url": None,
                "message": "未识别的伴随插件面板。",
            }

        dashboard = item.get("dashboard") or {}
        external_url = dashboard.get("external_url")
        official_page_url = dashboard.get("official_page_url")
        target_url = external_url
        open_url = external_url or official_page_url
        if target_url:
            message = None
        elif official_page_url:
            message = "AstrBot 插件页需要在 AstrBot Dashboard 中新窗口打开。"
        else:
            message = "该插件面板未开启或尚未检测到可用入口。"
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "role": item.get("role"),
            "available": bool(dashboard.get("available") and target_url),
            "target_url": target_url,
            "open_url": open_url,
            "external_url": external_url,
            "official_page_url": official_page_url,
            "label": dashboard.get("label") or "打开面板",
            "kind": dashboard.get("kind"),
            "active": bool(item.get("active")),
            "delegated": item.get("delegated"),
            "plugin": item.get("plugin") or {},
            "message": message,
        }

    def get_plugin_page_url(
        self,
        plugin_name: str,
        page_name: str,
        asset_path: str = "",
    ) -> Optional[str]:
        """Return an AstrBot Dashboard URL for known companion plugin Pages."""
        if str(page_name or "").strip() != LIVINGMEMORY_PAGE_NAME:
            return None

        delegation = self._delegation()
        star = delegation.memory_plugin() if delegation else None
        if not self._matches_livingmemory_plugin(plugin_name, star):
            return None

        runtime_name = getattr(star, "name", None) or "LivingMemory"
        return _plugin_page_content_url(
            self._astrbot_dashboard_base_url(),
            runtime_name,
            LIVINGMEMORY_PAGE_NAME,
            asset_path,
        )

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
                "route": "#/home",
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
        official_page_url = _plugin_page_content_url(
            self._astrbot_dashboard_base_url(),
            getattr(star, "name", None),
            LIVINGMEMORY_PAGE_NAME,
        ) if plugin else None
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
                "url": LIVINGMEMORY_EMBED_URL,
                "external_url": dashboard_url,
                "official_page_url": official_page_url,
                "route": "#/graphs",
                "label": "LivingMemory 面板" if dashboard_url else "AstrBot 插件页",
                "kind": "embedded_external" if dashboard_url else "astrbot_page",
                "astrbot_page": "插件 -> LivingMemory -> Pages -> dashboard",
            },
            "dev_api": {
                "base": LIVINGMEMORY_PAGE_API_BASE,
                "mode": "astrbot_register_web_api",
                "endpoints": LIVINGMEMORY_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    def _astrbot_dashboard_base_url(self) -> Optional[str]:
        astrbot_config = getattr(self.container, "astrbot_core_config", None)
        dashboard_config = _safe_get(astrbot_config, "dashboard")
        if dashboard_config is None:
            # Backward-compatible test/container fallback. The normal
            # runtime path uses astrbot_core_config so plugin settings are not
            # confused with AstrBot's global dashboard config.
            dashboard_config = _safe_get(
                getattr(self.container, "astrbot_config", None),
                "dashboard",
            )
        dashboard_config_provided = dashboard_config is not None
        dashboard_config = dashboard_config or {}
        env_host = _env_first("DASHBOARD_HOST", "ASTRBOT_DASHBOARD_HOST")
        env_port = _env_first("DASHBOARD_PORT", "ASTRBOT_DASHBOARD_PORT")
        if not dashboard_config_provided and env_host is None and env_port is None:
            return None

        if _safe_get(dashboard_config, "enable", True) is False:
            return None

        ssl_config = _safe_get(dashboard_config, "ssl", {}) or {}
        ssl_enabled = _bool_value(
            _env_first("DASHBOARD_SSL_ENABLE", "ASTRBOT_DASHBOARD_SSL_ENABLE"),
            bool(_safe_get(ssl_config, "enable", False)),
        )
        return _base_url(
            "https" if ssl_enabled else "http",
            env_host or _safe_get(dashboard_config, "host", "0.0.0.0"),
            env_port or _safe_get(dashboard_config, "port", 6185),
        )

    @staticmethod
    def _matches_livingmemory_plugin(plugin_name: Any, star: Any) -> bool:
        requested = str(plugin_name or "").strip().lower()
        if not requested:
            return False
        if requested in LIVINGMEMORY_PLUGIN_ALIASES:
            return True

        candidates = {
            getattr(star, "name", None),
            getattr(star, "display_name", None),
            getattr(star, "root_dir_name", None),
            getattr(star, "module_path", None),
        }
        module_path = getattr(star, "module_path", None)
        if isinstance(module_path, str):
            candidates.update(part for part in module_path.split(".") if part)
        return requested in {
            str(candidate).strip().lower()
            for candidate in candidates
            if str(candidate or "").strip()
        }

    def _group_chat_plus_dashboard(self, star: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(star, "star_cls", None)
        host = getattr(plugin, "web_panel_host", None)
        port = getattr(plugin, "web_panel_port", None)
        enabled = bool(getattr(plugin, "enable_web_panel", False))
        dashboard_url = _http_url(host, port) if enabled else None
        panel_url = _join_url(dashboard_url, "/panel?embed=1")

        return {
            "id": "group_chat_plus",
            "title": "Group Chat Plus",
            "role": "回复决策与生成",
            "active": star is not None,
            "delegated": bool(status.get("reply_delegated")),
            "plugin": self._star_info(star),
            "dashboard": {
                "available": bool(panel_url),
                "url": GROUP_CHAT_PLUS_EMBED_URL,
                "external_url": panel_url,
                "route": "#/reply-strategy",
                "label": "Group Chat Plus 面板",
                "kind": "embedded_external",
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
