import asyncio
import sys
import time
import urllib.error
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
    _probe_panel_reachable,
)


def _clear_probe_cache():
    integration_service_module._PANEL_PROBE_CACHE.clear()


def _star(name, plugin, *, root_dir_name=None):
    return SimpleNamespace(
        name=name,
        display_name=name,
        root_dir_name=root_dir_name or name,
        module_path=f"data.plugins.{root_dir_name or name}.main",
        star_cls=plugin,
    )


class _FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status


def _http_error(code):
    return urllib.error.HTTPError("http://127.0.0.1:1451/panel", code, "x", None, None)


def _dashboards_by_id(payload):
    return {item["id"]: item for item in payload["dashboards"]}


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

    _clear_probe_cache()
    with patch.object(
        integration_service_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(200),
    ):
        payload = await IntegrationService(container).get_status()
    _clear_probe_cache()

    dashboards = _dashboards_by_id(payload)
    assert payload["delegation"]["memory_delegated"] is True
    assert payload["hub"]["base_path"] == "/api/hub/v1"
    assert payload["hub"]["manifest_url"] == "/api/hub/v1/manifest"
    assert "POST /api/hub/v1/context" in payload["hub"]["endpoints"]
    assert payload["hub"]["capabilities"]["graphs"] is True
    assert dashboards["self_learning"]["dev_api"]["base"] == "/api"
    assert dashboards["self_learning"]["dev_api"]["hub_base"] == "/api/hub/v1"
    assert "POST /api/hub/v1/messages/ingest" in dashboards["self_learning"]["dev_api"]["endpoints"]
    assert dashboards["livingmemory"]["status"]["healthy"] is True
    assert dashboards["livingmemory"]["dashboard"]["external_url"] == "http://127.0.0.1:8888"
    assert dashboards["livingmemory"]["dashboard"]["route"] == "#/graphs"
    assert dashboards["livingmemory"]["dev_api"]["base"] == "/api/graphs"
    assert dashboards["livingmemory"]["dev_api"]["mode"] == "self_learning_graph_store_adapter"
    assert "GET /api/graphs/memory" in dashboards["livingmemory"]["dev_api"]["endpoints"]
    assert "POST /astrbot_plugin_livingmemory/page/graph/query" not in dashboards["livingmemory"]["dev_api"]["endpoints"]
    assert dashboards["group_chat_plus"]["status"] == {
        "healthy": True,
        "state": "ok",
        "message": "插件已加载，面板端口可达",
    }
    # issue #271：面板只保留状态标识与新窗口链接，不再有内嵌路由/回复策略页
    assert dashboards["group_chat_plus"]["dashboard"]["external_url"] == "http://127.0.0.1:8787/panel"
    assert "route" not in dashboards["group_chat_plus"]["dashboard"]
    assert "embeddable" not in dashboards["group_chat_plus"]["dashboard"]
    assert "embeddable" not in dashboards["livingmemory"]["dashboard"]
    assert "GET /api/data/overview" in dashboards["group_chat_plus"]["dev_api"]["endpoints"]
    assert not hasattr(IntegrationService, "get_embed_target")


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


async def test_probe_panel_reachable_caches_result():
    _clear_probe_cache()
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(str(request))
        return _FakeResponse(200)

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        assert await _probe_panel_reachable("http://127.0.0.1:1451/panel") is True
        assert await _probe_panel_reachable("http://127.0.0.1:1451/panel") is True
    assert len(calls) == 1
    _clear_probe_cache()


async def test_probe_panel_reachable_returns_false_when_unreachable():
    _clear_probe_cache()

    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        assert await _probe_panel_reachable("http://127.0.0.1:1451/panel") is False
    _clear_probe_cache()


async def test_probe_panel_reachable_treats_auth_required_as_reachable():
    _clear_probe_cache()

    def fake_urlopen(request, timeout=None):
        raise _http_error(401)

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        assert await _probe_panel_reachable("http://127.0.0.1:1451/panel") is True
    _clear_probe_cache()


async def test_probe_panel_reachable_treats_5xx_as_down():
    _clear_probe_cache()
    with patch.object(
        integration_service_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(503),
    ):
        assert await _probe_panel_reachable("http://127.0.0.1:1451/panel") is False
    _clear_probe_cache()


async def test_probe_panel_reachable_coalesces_concurrent_probes():
    _clear_probe_cache()
    calls = []

    def slow_urlopen(request, timeout=None):
        time.sleep(0.05)
        calls.append(str(request))
        return _FakeResponse(200)

    with patch.object(integration_service_module.urllib.request, "urlopen", slow_urlopen):
        results = await asyncio.gather(*[
            _probe_panel_reachable("http://127.0.0.1:1451/panel")
            for _ in range(5)
        ])
    assert results == [True] * 5
    assert len(calls) == 1
    _clear_probe_cache()


def _gcp_container(group_chat_plus):
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


async def test_group_chat_plus_reports_ok_when_panel_reachable():
    _clear_probe_cache()
    container = _gcp_container(SimpleNamespace(
        enable_web_panel=True,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    ))

    with patch.object(
        integration_service_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(200),
    ):
        payload = await IntegrationService(container).get_status()
    _clear_probe_cache()

    dashboard = _dashboards_by_id(payload)["group_chat_plus"]
    assert dashboard["active"] is True
    assert dashboard["status"]["healthy"] is True
    assert dashboard["status"]["state"] == "ok"
    assert dashboard["dashboard"]["available"] is True
    assert dashboard["dashboard"]["external_url"] == "http://127.0.0.1:8787/panel"


async def test_group_chat_plus_reports_offline_when_panel_unreachable():
    _clear_probe_cache()
    container = _gcp_container(SimpleNamespace(
        enable_web_panel=True,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    ))

    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    with patch.object(integration_service_module.urllib.request, "urlopen", fake_urlopen):
        payload = await IntegrationService(container).get_status()
    _clear_probe_cache()

    dashboard = _dashboards_by_id(payload)["group_chat_plus"]
    assert dashboard["status"]["healthy"] is False
    assert dashboard["status"]["state"] == "offline"
    assert "不可达" in dashboard["status"]["message"]
    assert dashboard["dashboard"]["available"] is True


async def test_group_chat_plus_reports_degraded_when_panel_disabled():
    container = _gcp_container(SimpleNamespace(
        enable_web_panel=False,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    ))

    payload = await IntegrationService(container).get_status()

    dashboard = _dashboards_by_id(payload)["group_chat_plus"]
    assert dashboard["active"] is True
    assert dashboard["status"]["healthy"] is False
    assert dashboard["status"]["state"] == "degraded"
    assert "未开启" in dashboard["status"]["message"]
    assert dashboard["dashboard"]["available"] is False
    assert dashboard["dashboard"]["external_url"] is None


async def test_group_chat_plus_reports_not_installed_without_plugin():
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_reply_to_group_chat_plus=True,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
        ),
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=SimpleNamespace(
            status=lambda: {
                "memory_delegated": False,
                "memory_plugin": None,
                "reply_delegated": False,
                "reply_plugin": None,
            },
            memory_plugin=lambda: None,
            reply_plugin=lambda: None,
        ),
    )

    payload = await IntegrationService(container).get_status()

    dashboard = _dashboards_by_id(payload)["group_chat_plus"]
    assert dashboard["active"] is False
    assert dashboard["status"]["healthy"] is None
    assert dashboard["status"]["state"] == "not_installed"
    assert dashboard["dashboard"]["available"] is False


def _lm_official_page_container(memory_star, *, astrbot_config=None):
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": True,
            "memory_plugin": "astrbot_plugin_livingmemory",
            "reply_delegated": False,
            "reply_plugin": None,
        },
        memory_plugin=lambda: memory_star,
        reply_plugin=lambda: None,
    )
    return SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_memory_to_livingmemory=True,
            livingmemory_plugin_name="astrbot_plugin_livingmemory",
            disable_local_memory_when_delegated=True,
            delegate_reply_to_group_chat_plus=False,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
            disable_local_reply_when_delegated=True,
            knowledge_engine="legacy",
            lightrag_query_mode="local",
        ),
        astrbot_config=astrbot_config,
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=delegation,
    )


def _force_legacy_hash_url():
    """钉住 legacy 路由前缀，避免断言随本机 AstrBot 版本漂移（CI 装 4.14，
    本地 venv 是 4.29+）。"""

    def _legacy(plugin_name, page_name):
        return f"#/plugin-page/{plugin_name}/{page_name}"

    return patch(
        "self_learning_EterU.utils.framework_compat.plugin_page_hash_url",
        _legacy,
    )


async def test_livingmemory_official_page_detected_from_plugin_pages(tmp_path):
    # LM 2.6.0+ 移除独立 WebUI，改为自带 AstrBot 官方插件页 pages/dashboard/index.html
    (tmp_path / "pages" / "dashboard").mkdir(parents=True)
    (tmp_path / "pages" / "dashboard" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    memory_star = SimpleNamespace(
        name="astrbot_plugin_livingmemory",
        display_name="astrbot_plugin_livingmemory",
        root_dir_name="astrbot_plugin_livingmemory",
        module_path=str(tmp_path / "main.py"),
        star_cls=SimpleNamespace(),
    )
    container = _lm_official_page_container(
        memory_star,
        astrbot_config={"dashboard": {"host": "0.0.0.0", "port": 6185}},
    )

    with _force_legacy_hash_url():
        payload = await IntegrationService(container).get_status()
    dashboards = _dashboards_by_id(payload)
    dashboard = dashboards["livingmemory"]["dashboard"]
    expected = (
        "http://127.0.0.1:6185/#/plugin-page/"
        "astrbot_plugin_livingmemory/dashboard"
    )
    assert dashboard["official_page_url"] == expected
    # 官方插件页只作为新窗口链接暴露（issue #271），不再作为 iframe 目标
    assert dashboard["external_url"] == expected
    assert dashboard["available"] is True
    assert dashboards["livingmemory"]["status"]["healthy"] is True
    assert dashboards["livingmemory"]["status"]["state"] == "ok"


async def test_livingmemory_official_page_resolves_dotted_module_path(tmp_path):
    # 生产环境 star/base.py 会把 StarMetadata.module_path 覆写为 cls.__module__
    # （点分导入路径），需通过 sys.modules 中已加载模块的 __file__ 还原插件目录。
    import types

    (tmp_path / "pages" / "dashboard").mkdir(parents=True)
    (tmp_path / "pages" / "dashboard" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    fake_module = types.ModuleType("data.plugins.astrbot_plugin_livingmemory.main")
    fake_module.__file__ = str(tmp_path / "main.py")
    memory_star = SimpleNamespace(
        name="astrbot_plugin_livingmemory",
        display_name="astrbot_plugin_livingmemory",
        root_dir_name="astrbot_plugin_livingmemory",
        module_path="data.plugins.astrbot_plugin_livingmemory.main",
        star_cls=SimpleNamespace(),
    )
    container = _lm_official_page_container(
        memory_star,
        astrbot_config={"dashboard": {"host": "0.0.0.0", "port": 6185}},
    )

    with _force_legacy_hash_url(), patch.dict(
        sys.modules,
        {"data.plugins.astrbot_plugin_livingmemory.main": fake_module},
    ):
        payload = await IntegrationService(container).get_status()

    dashboard = _dashboards_by_id(payload)["livingmemory"]["dashboard"]
    assert dashboard["official_page_url"] == (
        "http://127.0.0.1:6185/#/plugin-page/astrbot_plugin_livingmemory/dashboard"
    )


async def test_livingmemory_official_page_uses_plugin_view_route_on_4_29(tmp_path):
    # AstrBot v4.29 起 Pages 更名 Views，hash 路由随 framework_compat 门控切换
    (tmp_path / "pages" / "dashboard").mkdir(parents=True)
    (tmp_path / "pages" / "dashboard" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    memory_star = SimpleNamespace(
        name="astrbot_plugin_livingmemory",
        display_name="astrbot_plugin_livingmemory",
        root_dir_name="astrbot_plugin_livingmemory",
        module_path=str(tmp_path / "main.py"),
        star_cls=SimpleNamespace(),
    )
    container = _lm_official_page_container(
        memory_star,
        astrbot_config={"dashboard": {"host": "0.0.0.0", "port": 6185}},
    )

    with patch(
        "self_learning_EterU.utils.framework_compat.plugin_page_hash_prefix",
        return_value="#/plugin-view",
    ):
        payload = await IntegrationService(container).get_status()

    dashboard = _dashboards_by_id(payload)["livingmemory"]["dashboard"]
    assert dashboard["official_page_url"] == (
        "http://127.0.0.1:6185/#/plugin-view/astrbot_plugin_livingmemory/dashboard"
    )


def test_discover_plugin_pages_merges_roots_and_gates_by_version(tmp_path):
    # AstrBot v4.29 plugin_page_service.PLUGIN_PAGE_ROOT_DIR_NAMES = ("views", "pages")
    from self_learning_EterU.webui.services.integration_service import (
        _discover_plugin_pages,
    )

    def _patch_dir_names(names):
        return patch(
            "self_learning_EterU.utils.framework_compat.plugin_view_dir_names",
            return_value=names,
        )

    entry = str(tmp_path / "main.py")
    (tmp_path / "views" / "console").mkdir(parents=True)
    (tmp_path / "views" / "console" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    (tmp_path / "pages" / "legacy").mkdir(parents=True)
    (tmp_path / "pages" / "legacy" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    # v4.29：两个根目录页名合并返回（views 在前，去重保序）
    with _patch_dir_names(("views", "pages")):
        assert _discover_plugin_pages(entry) == ["console", "legacy"]

    # 旧版 AstrBot 只发现 pages/：向其暴露 views 页名会生成死链接
    with _patch_dir_names(("pages",)):
        assert _discover_plugin_pages(entry) == ["legacy"]

    # views 下存在无关页面时，pages 下的 dashboard 不得漏报
    import shutil

    shutil.rmtree(tmp_path / "views")
    (tmp_path / "views" / "unrelated").mkdir(parents=True)
    (tmp_path / "views" / "unrelated" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    with _patch_dir_names(("views", "pages")):
        assert _discover_plugin_pages(entry) == ["unrelated", "legacy"]

    # 同一目录内多个页面按字母序返回，不随文件系统迭代顺序漂移
    (tmp_path / "views" / "alpha").mkdir(parents=True)
    (tmp_path / "views" / "alpha" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    with _patch_dir_names(("views", "pages")):
        assert _discover_plugin_pages(entry) == ["alpha", "unrelated", "legacy"]


async def test_livingmemory_official_page_prefers_dashboard(tmp_path):
    # 多页面时官方页链接应优先指向 dashboard，而非排序首位的次要页面
    (tmp_path / "views" / "console").mkdir(parents=True)
    (tmp_path / "views" / "console" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    (tmp_path / "pages" / "dashboard").mkdir(parents=True)
    (tmp_path / "pages" / "dashboard" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    memory_star = SimpleNamespace(
        name="astrbot_plugin_livingmemory",
        display_name="astrbot_plugin_livingmemory",
        root_dir_name="astrbot_plugin_livingmemory",
        module_path=str(tmp_path / "main.py"),
        star_cls=SimpleNamespace(),
    )
    container = _lm_official_page_container(
        memory_star,
        astrbot_config={"dashboard": {"host": "0.0.0.0", "port": 6185}},
    )

    with _force_legacy_hash_url():
        payload = await IntegrationService(container).get_status()

    dashboard = _dashboards_by_id(payload)["livingmemory"]["dashboard"]
    assert dashboard["official_page_url"] == (
        "http://127.0.0.1:6185/#/plugin-page/astrbot_plugin_livingmemory/dashboard"
    )


async def test_livingmemory_official_page_absent_without_pages_or_origin(tmp_path):
    memory_star = SimpleNamespace(
        name="astrbot_plugin_livingmemory",
        display_name="astrbot_plugin_livingmemory",
        root_dir_name="astrbot_plugin_livingmemory",
        module_path=str(tmp_path / "main.py"),
        star_cls=SimpleNamespace(),
    )

    # 插件没有 pages/ 目录：无从推断官方页入口
    container = _lm_official_page_container(memory_star)
    payload = await IntegrationService(container).get_status()
    dashboard = _dashboards_by_id(payload)["livingmemory"]["dashboard"]
    assert dashboard["official_page_url"] is None
    assert dashboard["external_url"] is None

    # 有 pages/ 但容器没有 astrbot_config：拿不到 AstrBot Dashboard origin
    (tmp_path / "pages" / "dashboard").mkdir(parents=True)
    (tmp_path / "pages" / "dashboard" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    payload = await IntegrationService(container).get_status()
    dashboard = _dashboards_by_id(payload)["livingmemory"]["dashboard"]
    assert dashboard["official_page_url"] is None


def test_embed_route_removed_from_integrations_blueprint():
    """issue #271：iframe 嵌入壳端点必须整体移除，只保留状态标识。"""
    from self_learning_EterU.webui.blueprints.integrations import integrations_bp

    rules = [rule for rule, *_ in integrations_bp.registry._routes]
    assert all("embed" not in rule for rule in rules)
    assert "/integrations/status" in rules
