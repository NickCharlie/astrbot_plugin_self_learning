"""回归测试：内嵌插件页设置页「数据管理」与「Bug 反馈」的桥接路由。

独立 WebUI 设置页的数据管理面板由 /api/data/statistics 与 /api/data/clear/<target>
提供，Bug 反馈面板由 /api/bug_report/config 与 POST /api/bug_report 提供；内嵌页
只能经 ``page/*`` 桥接访问。本组用例锁定桥接复用同一组服务方法
（DataManagementService、BugReportService），且不可恢复的清空需页面确认。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.page_api import PAGE_API_PREFIX, PluginPageApi  # noqa: E402


class _FakeDataService:
    calls: list = []
    fail = False

    def __init__(self, container):
        self.container = container

    async def get_data_statistics(self):
        _FakeDataService.calls.append(("statistics",))
        if _FakeDataService.fail:
            raise ValueError("数据库管理器未初始化")
        return {"messages": 12, "persona_reviews": 3, "jargon": 5, "memory": 7}

    async def _clear(self, name, deleted):
        _FakeDataService.calls.append((name,))
        return True, f"已清除 {deleted} 条数据", deleted

    async def clear_messages(self):
        return await self._clear("clear_messages", 5)

    async def clear_persona_reviews(self):
        return await self._clear("clear_persona_reviews", 2)

    async def clear_style_learning(self):
        return await self._clear("clear_style_learning", 3)

    async def clear_jargon(self):
        return await self._clear("clear_jargon", 4)

    async def clear_learning_history(self):
        return await self._clear("clear_learning_history", 6)

    async def clear_all(self):
        return await self._clear("clear_all", 20)


class _FakeBugReportService:
    calls: list = []

    def __init__(self, container):
        self.container = container

    def get_bug_report_config(self):
        _FakeBugReportService.calls.append(("config",))
        return {
            "enabled": True,
            "defaultBuild": "v2.0",
            "severityOptions": [{"value": 3, "label": "3 - 一般"}],
            "logPreview": {"plugin_log": ""},
        }

    async def submit_bug_report(self, bug_data):
        _FakeBugReportService.calls.append(("submit", bug_data))
        if not bug_data.get("title"):
            return False, "缺少必需字段: title", None
        return True, "Bug报告提交成功", {"id": 42}


def _make_api(body=None) -> PluginPageApi:
    api = PluginPageApi(plugin=SimpleNamespace())
    container = SimpleNamespace(bound=True)
    api._imports = lambda: SimpleNamespace(
        get_container=lambda: container,
        DataManagementService=_FakeDataService,
        BugReportService=_FakeBugReportService,
    )
    api._query = lambda: {}

    async def _body():
        return body or {}

    api._body = _body
    _FakeDataService.calls = []
    _FakeDataService.fail = False
    _FakeBugReportService.calls = []
    return api


def test_data_and_bug_report_routes_registered_on_bridge():
    registered = []
    plugin = SimpleNamespace(
        context=SimpleNamespace(
            register_web_api=lambda route, handler, methods, description: registered.append((route, methods))
        )
    )
    PluginPageApi(plugin=plugin).register_routes()

    assert (f"{PAGE_API_PREFIX}/data/statistics", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/data/clear", ["POST"]) in registered
    assert (f"{PAGE_API_PREFIX}/bug-report", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/bug-report/submit", ["POST"]) in registered


def test_data_statistics_reuse_data_management_service():
    api = _make_api()

    result = asyncio.run(api.get_data_statistics())

    assert result["status"] == "ok"
    assert result["data"]["messages"] == 12
    assert _FakeDataService.calls == [("statistics",)]


def test_data_statistics_failure_is_soft_operation():
    api = _make_api()
    _FakeDataService.fail = True

    result = asyncio.run(api.get_data_statistics())

    assert result["data"]["success"] is False
    assert result["data"]["message"] == "请求处理失败，请稍后重试"


def test_data_clear_dispatches_each_target_to_service_method():
    expected = {
        "messages": "clear_messages",
        "persona_reviews": "clear_persona_reviews",
        "style_learning": "clear_style_learning",
        "jargon": "clear_jargon",
        "learning_history": "clear_learning_history",
        "all": "clear_all",
    }
    for target, method in expected.items():
        api = _make_api(body={"target": target, "confirmed": True})
        result = asyncio.run(api.post_data_clear())
        assert result["data"]["success"] is True, target
        assert isinstance(result["data"]["deleted"], int)
        assert _FakeDataService.calls == [(method,)]


def test_data_clear_requires_confirmation_and_known_target():
    api = _make_api(body={"target": "messages"})
    result = asyncio.run(api.post_data_clear())
    assert result["data"]["success"] is False
    assert _FakeDataService.calls == []

    api = _make_api(body={"target": "memory", "confirmed": True})
    result = asyncio.run(api.post_data_clear())
    assert result["data"]["success"] is False
    assert "未知清空目标" in result["data"]["message"]
    assert _FakeDataService.calls == []


def test_bug_report_config_reuses_bug_report_service():
    api = _make_api()

    result = asyncio.run(api.get_bug_report_config())

    assert result["data"]["enabled"] is True
    assert result["data"]["defaultBuild"] == "v2.0"
    assert _FakeBugReportService.calls == [("config",)]


def test_bug_report_submit_forwards_payload_and_reports_failure():
    payload = {"title": "无法打开审核详情", "steps": "1. 打开 WebUI", "severity": 3, "pri": 3, "type": "codeerror"}
    api = _make_api(body=payload)
    result = asyncio.run(api.post_bug_report())
    assert result["data"]["success"] is True
    assert result["data"]["message"] == "Bug报告提交成功"
    assert result["data"]["data"] == {"id": 42}
    assert _FakeBugReportService.calls == [("submit", payload)]

    api = _make_api(body={"steps": "x"})
    result = asyncio.run(api.post_bug_report())
    assert result["data"]["success"] is False
    assert "缺少必需字段" in result["data"]["message"]
