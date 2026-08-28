import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.services import integration_service as integration_service_module
from self_learning_EterU.webui.services.integration_service import (
    IntegrationService,
    _frame_headers_block,
    _probe_embeddable,
)
from self_learning_EterU.webui.blueprints.integrations import _render_embed_shell


def _clear_probe_cache():
    integration_service_module._EMBED_PROBE_CACHE.clear()


def _star(name, plugin, *, root_dir_name=None):
    return SimpleNamespace(
        name=name,
        display_name=name,
        root_dir_name=root_dir_name or name,
        module_path=f"data.plugins.{root_dir_name or name}.main",
        star_cls=plugin,
    )


async def test_integration_service_reports_companion_dashboards_and_dev_apis():
    livingmemory = SimpleNamespace(
        config_manager=SimpleNamespace(
            webui_settings={
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8888,
            }
        )
    )
    group_chat_plus = SimpleNamespace(
        enable_web_panel=True,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    )
    livingmemory_star = _star(
        "LivingMemory",
        livingmemory,
        root_dir_name="astrbot_plugin_livingmemory",
    )
    group_chat_plus_star = _star(
        "astrbot_plugin_group_chat_plus",
        group_chat_plus,
    )
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": True,
            "memory_plugin": "LivingMemory",
            "reply_delegated": True,
            "reply_plugin": "astrbot_plugin_group_chat_plus",
        },
        memory_plugin=lambda: livingmemory_star,
        reply_plugin=lambda: group_chat_plus_star,
    )
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_memory_to_livingmemory=True,
            livingmemory_plugin_name="LivingMemory",
            disable_local_memory_when_delegated=True,
            delegate_reply_to_group_chat_plus=True,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
            disable_local_reply_when_delegated=True,
            knowledge_engine="legacy",
            lightrag_query_mode="local",
        ),
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=delegation,
    )

    payload = await IntegrationService(container).get_status()

    dashboards = {item["id"]: item for item in payload["dashboards"]}
    assert payload["delegation"]["memory_delegated"] is True
    assert payload["hub"]["base_path"] == "/api/hub/v1"
    assert payload["hub"]["manifest_url"] == "/api/hub/v1/manifest"
    assert "POST /api/hub/v1/context" in payload["hub"]["endpoints"]
    assert payload["hub"]["capabilities"]["graphs"] is True
    assert dashboards["self_learning"]["dev_api"]["base"] == "/api"
    assert dashboards["self_learning"]["dev_api"]["hub_base"] == "/api/hub/v1"
    assert "POST /api/hub/v1/messages/ingest" in dashboards["self_learning"]["dev_api"]["endpoints"]
    assert dashboards["livingmemory"]["dashboard"]["url"] == "/api/integrations/embed/livingmemory"
    assert dashboards["livingmemory"]["dashboard"]["external_url"] == "http://127.0.0.1:8888"
    assert dashboards["livingmemory"]["dashboard"]["route"] == "#/graphs"
    assert dashboards["livingmemory"]["dev_api"]["base"] == "/api/graphs"
    assert dashboards["livingmemory"]["dev_api"]["mode"] == "self_learning_graph_store_adapter"
    assert "GET /api/graphs/memory" in dashboards["livingmemory"]["dev_api"]["endpoints"]
    assert "POST /astrbot_plugin_livingmemory/page/graph/query" not in dashboards["livingmemory"]["dev_api"]["endpoints"]
    assert dashboards["group_chat_plus"]["dashboard"]["url"] == "/api/integrations/embed/group_chat_plus"
    assert dashboards["group_chat_plus"]["dashboard"]["external_url"] == "http://127.0.0.1:8787/panel?embed=1"
    assert dashboards["group_chat_plus"]["dashboard"]["route"] == "#/reply-strategy"
    assert "GET /api/data/overview" in dashboards["group_chat_plus"]["dev_api"]["endpoints"]

    livingmemory_embed = await IntegrationService(container).get_embed_target("livingmemory")
    group_chat_plus_embed = await IntegrationService(container).get_embed_target("reply-strategy")
    assert livingmemory_embed["target_url"] == "http://127.0.0.1:8888"
    assert group_chat_plus_embed["target_url"] == "http://127.0.0.1:8787/panel?embed=1"


async def test_integration_service_reports_high_cost_v2_warning():
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_memory_to_livingmemory=True,
            livingmemory_plugin_name="LivingMemory",
            disable_local_memory_when_delegated=True,
            delegate_reply_to_group_chat_plus=True,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
            disable_local_reply_when_delegated=True,
            knowledge_engine="lightrag",
            lightrag_query_mode="mix",
        ),
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=SimpleNamespace(
            status=lambda: {
                "memory_delegated": True,
                "memory_plugin": "LivingMemory",
                "reply_delegated": False,
                "reply_plugin": None,
            },
            memory_plugin=lambda: None,
            reply_plugin=lambda: None,
        ),
    )

    payload = await IntegrationService(container).get_status()

    assert payload["warnings"]
    assert "LivingMemory" in payload["warnings"][0]
    assert "token" in payload["warnings"][0]


def test_embed_shell_resolves_loopback_target_from_browser_host():
    html = _render_embed_shell({
        "title": "Group Chat Plus",
        "role": "回复决策与生成",
        "available": True,
        "target_url": "http://127.0.0.1:1451/panel?embed=1",
        "active": True,
        "delegated": True,
        "kind": "embedded_external",
    })

    assert 'src="http://127.0.0.1:1451' not in html
    assert 'href="http://127.0.0.1:1451' not in html
    assert 'data-target-url="http://127.0.0.1:1451/panel?embed=1"' in html
    assert "window.location.hostname" in html
    assert "target.host = target.port" in html


class _FakeResponse:
    def __init__(self, headers):
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


DASHBOARD_ORIGIN = "http://127.0.0.1:8989"


def test_frame_headers_block_rules():
    assert _frame_headers_block({"X-Frame-Options": "DENY"})
    assert _frame_headers_block({"X-Frame-Options": "SAMEORIGIN"})
    assert _frame_headers_block({"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"})
    assert _frame_headers_block({"Content-Security-Policy": "frame-ancestors 'self'"}, DASHBOARD_ORIGIN)
    assert _frame_headers_block({"Content-Security-Policy": "frame-ancestors *"}, None) is False
    assert not _frame_headers_block({"Content-Security-Policy": "default-src 'self'"}, DASHBOARD_ORIGIN)
    assert not _frame_headers_block({}, DASHBOARD_ORIGIN)


def test_frame_headers_allowlist_matches_parent_origin():
    blocked = {"Content-Security-Policy": "frame-ancestors 'self'"}
    allowed = {"Content-Security-Policy": "frame-ancestors 'self' http://127.0.0.1:8989"}
    assert _frame_headers_block(allowed, DASHBOARD_ORIGIN) is False
    assert _frame_headers_block(allowed, "http://192.168.1.5:8989") is True
    assert _frame_headers_block(blocked, DASHBOARD_ORIGIN) is True
    assert _frame_headers_block(
        {"Content-Security-Policy": "frame-ancestors http://*.example.com"},
        "http://a.example.com",
    ) is False
    assert _frame_headers_block(
        {"Content-Security-Policy": "frame-ancestors http://*.example.com:8989"},
        "http://a.example.com:9999",
    ) is True
    assert _frame_headers_block(
        {"Content-Security-Policy": "frame-ancestors https://127.0.0.1:8989"},
        DASHBOARD_ORIGIN,
    ) is True
    # 拿不到父页面 origin 时保守处理：仅 'self' 视为拒绝，含显式主机视为可能允许
    assert _frame_headers_block(blocked, None) is True
    assert _frame_headers_block(allowed, None) is False


async def test_probe_embeddable_caches_result():
    _clear_probe_cache()
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(str(request))
        return _FakeResponse({"X-Frame-Options": "DENY"})

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        assert await _probe_embeddable("http://127.0.0.1:1451/panel?embed=1") is False
        assert await _probe_embeddable("http://127.0.0.1:1451/panel?embed=1") is False
    assert len(calls) == 1
    _clear_probe_cache()


async def test_probe_embeddable_returns_none_when_unreachable():
    _clear_probe_cache()

    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        assert await _probe_embeddable("http://127.0.0.1:1451/panel?embed=1") is None
    _clear_probe_cache()


async def test_probe_embeddable_coalesces_concurrent_probes():
    _clear_probe_cache()
    calls = []

    def slow_urlopen(request, timeout=None):
        time.sleep(0.05)
        calls.append(str(request))
        return _FakeResponse({"X-Frame-Options": "DENY"})

    with patch.object(integration_service_module.urllib.request, "urlopen", slow_urlopen):
        results = await asyncio.gather(*[
            _probe_embeddable("http://127.0.0.1:1451/panel?embed=1")
            for _ in range(5)
        ])
    assert results == [False] * 5
    assert len(calls) == 1
    _clear_probe_cache()


def _gcp_container():
    group_chat_plus = SimpleNamespace(
        enable_web_panel=True,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    )
    group_chat_plus_star = _star("astrbot_plugin_group_chat_plus", group_chat_plus)
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": False,
            "memory_plugin": None,
            "reply_delegated": True,
            "reply_plugin": "astrbot_plugin_group_chat_plus",
        },
        memory_plugin=lambda: None,
        reply_plugin=lambda: group_chat_plus_star,
    )
    return SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_memory_to_livingmemory=False,
            delegate_reply_to_group_chat_plus=True,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
            disable_local_reply_when_delegated=True,
        ),
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=delegation,
    )


async def test_group_chat_plus_blocked_panel_degrades_to_external():
    _clear_probe_cache()
    container = _gcp_container()

    with patch.object(
        integration_service_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse({"X-Frame-Options": "DENY"}),
    ):
        payload = await IntegrationService(container).get_status()
        embed = await IntegrationService(container).get_embed_target("reply-strategy")

    dashboards = {item["id"]: item for item in payload["dashboards"]}
    dashboard = dashboards["group_chat_plus"]["dashboard"]
    assert dashboard["embeddable"] is False
    assert dashboard["kind"] == "external"
    assert dashboard["available"] is True
    assert embed["embeddable"] is False
    assert embed["available"] is True
    assert "新窗口" in embed["message"]
    _clear_probe_cache()


def test_embed_shell_renders_notice_when_panel_blocks_embedding():
    html = _render_embed_shell({
        "title": "Group Chat Plus",
        "role": "回复决策与生成",
        "available": True,
        "embeddable": False,
        "target_url": "http://127.0.0.1:1451/panel?embed=1",
        "active": True,
        "delegated": True,
        "kind": "external",
        "message": "面板禁止 iframe 嵌入，请在新窗口打开独立面板。",
    })

    assert "<iframe" not in html
    assert "面板禁止内嵌" in html
    assert "面板禁止 iframe 嵌入" in html
    assert 'data-target-url="http://127.0.0.1:1451/panel?embed=1"' in html
    assert "新窗口打开" in html


def test_embed_shell_keeps_iframe_when_embedding_allowed():
    html = _render_embed_shell({
        "title": "Group Chat Plus",
        "role": "回复决策与生成",
        "available": True,
        "embeddable": True,
        "target_url": "http://127.0.0.1:1451/panel?embed=1",
        "active": True,
        "delegated": True,
        "kind": "embedded_external",
    })

    assert '<iframe id="companion-frame"' in html
    assert "面板禁止内嵌" not in html
