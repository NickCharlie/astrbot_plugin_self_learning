"""Integration status service for companion plugin dashboards."""

from __future__ import annotations

import asyncio
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

try:
    from ...config import get_config_cost_warnings
except ImportError:
    from config import get_config_cost_warnings

LIVINGMEMORY_EMBED_URL = "/api/integrations/embed/livingmemory"
GROUP_CHAT_PLUS_EMBED_URL = "/api/integrations/embed/group_chat_plus"

_EMBED_PROBE_TIMEOUT = 2.0
_EMBED_PROBE_TTL = 60.0
_EMBED_PROBE_CACHE: Dict[str, Tuple[float, Optional[bool]]] = {}
_EMBED_PROBE_INFLIGHT: Dict[str, "asyncio.Future"] = {}

SELF_LEARNING_API_ENDPOINTS = [
    "GET /api/integrations/status",
    "POST /api/integrations/worldbook/preview",
    "POST /api/integrations/worldbook/import",
    "GET /api/integrations/worldbook/imports",
    "POST /api/integrations/qq-chat-history/preview",
    "POST /api/integrations/qq-chat-history/import",
    "GET /api/hub/v1/manifest",
    "GET /api/hub/v1/status",
    "POST /api/hub/v1/context",
    "POST /api/hub/v1/memories/remember",
    "POST /api/hub/v1/messages/ingest",
    "POST /api/hub/v1/learning/trigger",
    "GET /api/hub/v1/reviews",
    "POST /api/hub/v1/reviews/<review_id>/decision",
    "GET /api/hub/v1/graphs/memory",
    "GET /api/hub/v1/graphs/knowledge",
    "GET /api/hub/v1/metrics",
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
    "GET /api/graphs/memory",
    "GET /api/graphs/knowledge",
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


def _join_url(base_url: Optional[str], path: str) -> Optional[str]:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _frame_headers_block(headers: Any, parent_origin: Optional[str] = None) -> bool:
    """判断响应头是否禁止父页面（self_learning WebUI）以 iframe 嵌入。"""
    xfo = str(headers.get("X-Frame-Options", "") or "").strip().strip("'\"").lower()
    if xfo in {"deny", "sameorigin"}:
        return True
    csp = str(headers.get("Content-Security-Policy", "") or "").lower()
    for directive in csp.split(";"):
        parts = directive.split()
        if parts and parts[0] == "frame-ancestors":
            sources = [value.strip("'\"") for value in parts[1:]]
            if not sources or "none" in sources:
                return True
            if "*" in sources:
                return False
            if parent_origin:
                return not any(
                    _source_allows_origin(source, parent_origin) for source in sources
                )
            # 拿不到父页面 origin 时保守处理：'self' 只放行面板自身源（与嵌入页
            # 必然不同源），视为拒绝；列表含显式主机时无从比对，视为可能允许。
            return all(source in {"self", "none"} for source in sources)
    return False


def _source_allows_origin(source: str, origin: str) -> bool:
    """判断单个 frame-ancestors source 表达式是否放行给定父页面 origin。"""
    source = source.strip("'\"").lower()
    if not source or source in {"self", "none"}:
        return False
    if source == "*":
        return True
    try:
        origin_parts = urlsplit(origin)
        expr = urlsplit(source if "//" in source else f"//{source}")
        expr_host = (expr.hostname or "").lower()
        origin_host = (origin_parts.hostname or "").lower()
        if not expr_host or not origin_host:
            return False
        if expr_host.startswith("*."):
            if not (
                origin_host == expr_host[2:] or origin_host.endswith(expr_host[1:])
            ):
                return False
        elif expr_host != origin_host:
            return False
        if expr.port is not None and expr.port != origin_parts.port:
            return False
        if expr.scheme and expr.scheme != origin_parts.scheme:
            return False
        return True
    except ValueError:
        return False


async def _probe_embeddable(
    url: str, parent_origin: Optional[str] = None
) -> Optional[bool]:
    """探测伴随面板是否允许 iframe 嵌入。

    返回 True=允许、False=被响应头阻止、None=不可达。结果缓存 60 秒；阻塞的
    HTTP 请求放进 executor 执行，避免卡住 Quart 事件循环；同一 URL 的并发
    未命中探测通过 in-flight future 合并为一次请求。
    """
    key = f"{parent_origin or ''}|{url}"
    now = time.time()
    cached = _EMBED_PROBE_CACHE.get(key)
    if cached and now - cached[0] < _EMBED_PROBE_TTL:
        return cached[1]
    inflight = _EMBED_PROBE_INFLIGHT.get(key)
    if inflight is not None:
        return await asyncio.shield(inflight)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _EMBED_PROBE_INFLIGHT[key] = future
    try:
        result = await loop.run_in_executor(
            None, _probe_embeddable_sync, url, parent_origin
        )
        _EMBED_PROBE_CACHE[key] = (time.time(), result)
        if not future.done():
            future.set_result(result)
        return result
    except Exception:
        if not future.done():
            future.set_result(None)
        raise
    finally:
        _EMBED_PROBE_INFLIGHT.pop(key, None)


def _probe_embeddable_sync(
    url: str, parent_origin: Optional[str]
) -> Optional[bool]:
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "self-learning-embed-probe"}
        )
        with urllib.request.urlopen(request, timeout=_EMBED_PROBE_TIMEOUT) as response:
            return not _frame_headers_block(response.headers, parent_origin)
    except Exception:
        return None


class IntegrationService:
    """Build a small runtime map of delegated capabilities and dashboards."""

    def __init__(self, container: Any) -> None:
        self.container = container

    async def get_status(self) -> Dict[str, Any]:
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
            "warnings": get_config_cost_warnings(config),
            "dashboards": [
                self._self_learning_dashboard(),
                self._livingmemory_dashboard(memory_star, status),
                await self._group_chat_plus_dashboard(reply_star, status),
            ],
            "hub": self._hub_contract(config),
        }

    async def get_embed_target(self, plugin_id: str) -> Dict[str, Any]:
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

        payload = await self.get_status()
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
        target_url = external_url or official_page_url
        embeddable = dashboard.get("embeddable")
        blocked = embeddable is False
        if blocked:
            message = "该面板设置了 X-Frame-Options/frame-ancestors，禁止 iframe 嵌入，请使用新窗口打开。"
        elif not target_url:
            message = "该插件面板未开启或尚未检测到可用入口。"
        else:
            message = None
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "role": item.get("role"),
            "available": bool(dashboard.get("available") and target_url),
            "embeddable": embeddable,
            "target_url": target_url,
            "external_url": external_url,
            "official_page_url": official_page_url,
            "label": dashboard.get("label") or "打开面板",
            "kind": dashboard.get("kind"),
            "active": bool(item.get("active")),
            "delegated": item.get("delegated"),
            "plugin": item.get("plugin") or {},
            "message": message,
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
        from .hub_service import HubService

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
                "hub_base": HubService.BASE_PATH,
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
                "url": LIVINGMEMORY_EMBED_URL,
                "external_url": dashboard_url,
                "official_page_url": None,
                "route": "#/graphs",
                "label": "本地图谱",
                "kind": "embedded_external" if dashboard_url else "local_graph",
                "graph_source": "Self Learning 直读 LivingMemory graph_store 后端对象",
            },
            "dev_api": {
                "base": "/api/graphs",
                "mode": "self_learning_graph_store_adapter",
                "endpoints": LIVINGMEMORY_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    def _dashboard_origin(self) -> Optional[str]:
        """父页面（self_learning WebUI / AstrBot Dashboard）的 origin。"""
        webui_config = getattr(self.container, "webui_config", None)
        return _http_url(
            getattr(webui_config, "host", "127.0.0.1"),
            getattr(webui_config, "port", None),
        )

    async def _group_chat_plus_dashboard(self, star: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(star, "star_cls", None)
        host = getattr(plugin, "web_panel_host", None)
        port = getattr(plugin, "web_panel_port", None)
        enabled = bool(getattr(plugin, "enable_web_panel", False))
        dashboard_url = _http_url(host, port) if enabled else None
        panel_url = _join_url(dashboard_url, "/panel?embed=1")

        # 自 v1.2.x 起 Group Chat Plus 面板固定返回 X-Frame-Options: DENY 与
        # frame-ancestors 'none'，iframe 嵌入会被浏览器静默拦截。此处探测真实
        # 响应头：被阻止时降级为 external，由嵌入壳提示改用新窗口打开。
        embeddable = (
            await _probe_embeddable(panel_url, self._dashboard_origin())
            if panel_url
            else None
        )
        blocked = embeddable is False

        return {
            "id": "group_chat_plus",
            "title": "Group Chat Plus",
            "role": "回复决策与生成",
            "active": star is not None,
            "delegated": bool(status.get("reply_delegated")),
            "plugin": self._star_info(star),
            "dashboard": {
                "available": bool(panel_url),
                "embeddable": embeddable,
                "url": GROUP_CHAT_PLUS_EMBED_URL,
                "external_url": panel_url,
                "route": "#/reply-strategy",
                "label": "Group Chat Plus 面板",
                "kind": "external" if blocked else "embedded_external",
                "message": (
                    "面板禁止 iframe 嵌入，请在新窗口打开独立面板。" if blocked else None
                ),
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

    def _hub_contract(self, config: Any) -> Dict[str, Any]:
        from .hub_service import HubService

        return {
            "name": "self-learning-hub",
            "version": HubService.API_VERSION,
            "base_path": HubService.BASE_PATH,
            "manifest_url": f"{HubService.BASE_PATH}/manifest",
            "status_url": f"{HubService.BASE_PATH}/status",
            "auth": {
                "api_key_enabled": bool(getattr(config, "enable_api_auth", False)),
                "schemes": ["Authorization: Bearer <api_key>", "X-Self-Learning-Key"],
            },
            "capabilities": HubService(self.container).capabilities(),
            "endpoints": [
                f"{endpoint['method']} {endpoint['path']}"
                for endpoint in HubService.endpoints()
            ],
        }
