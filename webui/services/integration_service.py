"""Integration status service for companion plugin dashboards."""

from __future__ import annotations

import asyncio
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ...config import get_config_cost_warnings
except ImportError:
    from config import get_config_cost_warnings

_PANEL_PROBE_TIMEOUT = 2.0
_PANEL_PROBE_TTL = 60.0
_PANEL_PROBE_CACHE: Dict[str, Tuple[float, Optional[bool]]] = {}
_PANEL_PROBE_INFLIGHT: Dict[str, "asyncio.Future"] = {}

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


def _astrbot_dashboard_origin(astrbot_config: Any) -> Optional[str]:
    """AstrBot Dashboard 的本机 origin（host/port 取自主配置 dashboard 段）。"""
    dashboard = _safe_get(astrbot_config, "dashboard")
    if dashboard is None:
        return None
    return _http_url(_safe_get(dashboard, "host", "0.0.0.0"), _safe_get(dashboard, "port"))


def _discover_plugin_pages(module_path: Any) -> List[str]:
    """列出插件 ``views/``（或旧约定 ``pages/``）下带 index.html 的页面名。

    AstrBot 官方插件页约定：v4.29 起 View 目录优先 ``views/``，同时兼容
    ``pages/``（``plugin_page_service.PLUGIN_PAGE_ROOT_DIR_NAMES``）。目录
    优先级经 :func:`plugin_view_dir_names` 随 AstrBot 版本门控——旧版页面
    服务不发现 ``views/``，向其暴露 views 页名会生成死链接。两个根目录的
    页名合并返回（views 在前），避免 views 下存在无关页面时漏报 pages 下
    的 dashboard。

    AstrBot 的 ``StarMetadata.module_path`` 可能是插件入口文件路径，也可能是
    点分导入路径（``star/base.py`` 会用 ``cls.__module__`` 覆写，如
    ``data.plugins.<插件名>.main``）。后者通过 ``sys.modules`` 里已加载模块的
    ``__file__`` 还原插件目录；页面目录位于入口文件自身或上级目录下，无法
    定位时返回空列表。
    """
    if not module_path:
        return []
    raw = str(module_path).strip()
    if not raw:
        return []

    from ...utils.framework_compat import plugin_view_dir_names

    bases: List[Path] = []
    base = Path(raw)
    bases.extend((base, base.parent))
    module = sys.modules.get(raw)
    module_file = getattr(module, "__file__", None)
    if module_file:
        module_base = Path(module_file)
        bases.extend((module_base, module_base.parent))

    for candidate in bases:
        names: List[str] = []
        for dir_name in plugin_view_dir_names():
            pages_root = candidate / dir_name
            try:
                if not pages_root.is_dir():
                    continue
                names.extend(
                    sorted(
                        item.name
                        for item in pages_root.iterdir()
                        if item.is_dir() and (item / "index.html").is_file()
                    )
                )
            except OSError:
                continue
        deduped = list(dict.fromkeys(names))
        if deduped:
            return deduped
    return []


async def _probe_panel_reachable(url: str) -> Optional[bool]:
    """探测伴随插件面板端口当前是否可达。

    返回 True=可达、False=连接失败、None=探测异常。结果缓存 60 秒；阻塞的
    HTTP 请求放进 executor 执行，避免卡住 Quart 事件循环；同一 URL 的并发
    未命中探测通过 in-flight future 合并为一次请求。
    """
    key = url
    now = time.time()
    cached = _PANEL_PROBE_CACHE.get(key)
    if cached and now - cached[0] < _PANEL_PROBE_TTL:
        return cached[1]
    inflight = _PANEL_PROBE_INFLIGHT.get(key)
    if inflight is not None:
        return await asyncio.shield(inflight)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _PANEL_PROBE_INFLIGHT[key] = future
    try:
        result = await loop.run_in_executor(None, _probe_panel_reachable_sync, url)
        _PANEL_PROBE_CACHE[key] = (time.time(), result)
        if not future.done():
            future.set_result(result)
        return result
    except BaseException:
        # 发起方被取消时（CancelledError 不走 except Exception）也要放行
        # 同 URL 的等待者，否则它们会在 shield(inflight) 上永久挂起
        if not future.done():
            future.set_result(None)
        raise
    finally:
        _PANEL_PROBE_INFLIGHT.pop(key, None)


def _probe_panel_reachable_sync(url: str) -> Optional[bool]:
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "self-learning-panel-health"}
        )
        with urllib.request.urlopen(request, timeout=_PANEL_PROBE_TIMEOUT) as response:
            status = getattr(response, "status", None) or response.getcode()
            return bool(status and status < 500)
    except urllib.error.HTTPError as exc:
        # 4xx（如面板要求登录）说明面板进程仍在响应，视为可达
        return 400 <= exc.code < 500
    except (OSError, urllib.error.URLError):
        return False
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
            "status": {
                "healthy": True,
                "state": "ok",
                "message": "本插件监控板运行中",
            },
            "dashboard": {
                "available": True,
                # 无 external_url：本卡片的入口就是当前监控板内部路由
                "route": "#/home",
                "label": "本插件监控板",
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

        # LivingMemory 2.7.0 移除了独立 WebUI（webui_settings 与随附端口服务），
        # 官方插件页成为唯一面板入口；旧版本仍可能带独立面板，保留探测以兼容。
        dashboard_url = None
        if _safe_get(webui_settings, "enabled", False):
            dashboard_url = _http_url(
                _safe_get(webui_settings, "host", "127.0.0.1"),
                _safe_get(webui_settings, "port", 8888),
            )

        official_page_url = self._livingmemory_official_page_url(star)

        if star is None:
            status_block = {
                "healthy": None,
                "state": "not_installed",
                "message": "未检测到 LivingMemory 插件",
            }
        else:
            status_block = {
                "healthy": True,
                "state": "ok",
                "message": "插件已加载",
            }

        return {
            "id": "livingmemory",
            "title": "LivingMemory",
            "role": "长期记忆与图谱",
            "active": star is not None,
            "delegated": bool(status.get("memory_delegated")),
            "plugin": self._star_info(star),
            "status": status_block,
            "dashboard": {
                "available": bool(dashboard_url or plugin or official_page_url),
                "external_url": dashboard_url or official_page_url,
                "official_page_url": official_page_url,
                "route": "#/graphs",
                "label": "本地图谱",
                "graph_source": "Self Learning 直读 LivingMemory graph_store 后端对象",
            },
            "dev_api": {
                "base": "/api/graphs",
                "mode": "self_learning_graph_store_adapter",
                "endpoints": LIVINGMEMORY_API_ENDPOINTS,
            },
            "settings_group": "Integration_Settings",
        }

    def _livingmemory_official_page_url(self, star: Any) -> Optional[str]:
        """LivingMemory 2.6.0+ 自带 AstrBot 官方插件页（views|pages/<页名>/index.html）。

        用户入口是 AstrBot Dashboard 前端 hash 路由（v4.29 起
        ``/#/plugin-view/<插件名>/<页名>``，旧版本 ``/#/plugin-page/...``），
        打开时复用浏览器内 AstrBot 会话。面板不再以 iframe 内嵌（issue #271：
        官方页固定 X-Frame-Options: SAMEORIGIN，内嵌必被浏览器拦截），只作为
        新窗口链接暴露。
        """
        astrbot_config = getattr(self.container, "astrbot_config", None)
        origin = _astrbot_dashboard_origin(astrbot_config)
        if not origin or star is None:
            return None
        plugin_name = str(getattr(star, "name", "") or "").strip()
        pages = _discover_plugin_pages(getattr(star, "module_path", None))
        if not plugin_name or not pages:
            return None
        from ...utils.framework_compat import plugin_page_hash_url

        # 多页面时优先指向 dashboard（监控面板），避免链接到次要页面
        page = "dashboard" if "dashboard" in pages else pages[0]
        return f"{origin}/{plugin_page_hash_url(plugin_name, page)}"

    async def _group_chat_plus_dashboard(self, star: Any, status: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(star, "star_cls", None)
        host = getattr(plugin, "web_panel_host", None)
        port = getattr(plugin, "web_panel_port", None)
        enabled = bool(getattr(plugin, "enable_web_panel", False))
        origin_url = _http_url(host, port) if enabled else None
        panel_url = _join_url(origin_url, "/panel")

        if star is None:
            status_block = {
                "healthy": None,
                "state": "not_installed",
                "message": "未检测到 Group Chat Plus 插件",
            }
        elif not panel_url:
            status_block = {
                "healthy": False,
                "state": "degraded",
                "message": "插件已加载，但 Web 面板未开启（enable_web_panel）",
            }
        else:
            # 面板只在状态页做可达性标识，不再 iframe 内嵌（issue #271：
            # GCP v1.2.x 起固定 X-Frame-Options: DENY，内嵌必被浏览器拦截）。
            reachable = await _probe_panel_reachable(panel_url)
            if reachable:
                status_block = {
                    "healthy": True,
                    "state": "ok",
                    "message": "插件已加载，面板端口可达",
                }
            elif reachable is None:
                status_block = {
                    "healthy": None,
                    "state": "unknown",
                    "message": "面板可达性探测失败，请手动确认",
                }
            else:
                status_block = {
                    "healthy": False,
                    "state": "offline",
                    "message": "插件已加载，但面板端口不可达",
                }

        return {
            "id": "group_chat_plus",
            "title": "Group Chat Plus",
            "role": "回复决策与生成",
            "active": star is not None,
            "delegated": bool(status.get("reply_delegated")),
            "plugin": self._star_info(star),
            "status": status_block,
            "dashboard": {
                "available": bool(panel_url),
                "external_url": panel_url,
                "label": "Group Chat Plus 面板",
            },
            "dev_api": {
                # base 必须是面板 origin（不带 /panel 路径），端点列表均为 /api/...
                "base": f"{origin_url}/api" if origin_url else "/api",
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
