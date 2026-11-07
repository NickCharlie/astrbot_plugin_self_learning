"""回归测试：内嵌插件页图谱「社交关系」视图的桥接路由。

独立 WebUI 图谱页的社交关系视图由 /api/social_relations/groups、
/api/social_relations/<group_id> 与 analyze / clear / share 子路由提供；内嵌页只能
经 ``page/*`` 桥接访问。本组用例锁定桥接复用同一组服务方法（SocialService、
GraphShareService）、不可恢复的清空需页面确认，以及分享链接指向独立 WebUI。
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


class _FakeSocialService:
    calls: list = []
    fail = False

    def __init__(self, container):
        self.container = container

    async def get_available_groups(self):
        _FakeSocialService.calls.append(("groups",))
        if _FakeSocialService.fail:
            raise RuntimeError("db offline")
        return [{"group_id": "g1", "message_count": 8, "member_count": 2, "relation_count": 1}]

    async def get_social_relations(self, group_id):
        _FakeSocialService.calls.append(("relations", group_id))
        return {
            "success": True,
            "group_id": group_id,
            "members": [{"user_id": "u1", "nickname": "小明", "message_count": 5}],
            "relations": [{"source": "u1", "target": "u2", "strength": 0.8}],
            "member_count": 1,
            "relation_count": 1,
            "message_count": 5,
        }

    async def trigger_analysis(self, group_id):
        _FakeSocialService.calls.append(("analyze", group_id))
        return True, f"群组 {group_id} 的社交关系分析已完成，发现 1 条关系"

    async def clear_relations(self, group_id):
        _FakeSocialService.calls.append(("clear", group_id))
        return True, f"群组 {group_id} 的社交关系数据已清空"


class _FakeGraphShareService:
    MIN_EXPIRES_HOURS = 1
    MAX_EXPIRES_HOURS = 720
    calls: list = []

    def __init__(self, container):
        self.container = container

    def create_share(self, group_id, expires_hours=168):
        _FakeGraphShareService.calls.append((group_id, expires_hours))
        return {
            "token": "tok_abcdefghijklmnopqrstuvwxyz",
            "group_id": group_id,
            "expires_hours": expires_hours,
            "expires_at_iso": "2026-11-14T00:00:00Z",
        }


def _make_api(query=None, body=None, *, webui_enabled=True) -> PluginPageApi:
    plugin = SimpleNamespace(
        plugin_config=SimpleNamespace(
            enable_web_interface=webui_enabled,
            web_interface_host="0.0.0.0",
            web_interface_port=7833,
        )
    )
    api = PluginPageApi(plugin=plugin)
    container = SimpleNamespace(bound=True, webui_config=None)
    api._imports = lambda: SimpleNamespace(
        get_container=lambda: container,
        SocialService=_FakeSocialService,
        GraphShareService=_FakeGraphShareService,
    )
    api._query = lambda: query or {}

    async def _body():
        return body or {}

    api._body = _body
    _FakeSocialService.calls = []
    _FakeSocialService.fail = False
    _FakeGraphShareService.calls = []
    return api


def test_social_graph_routes_registered_on_bridge():
    registered = []
    plugin = SimpleNamespace(
        context=SimpleNamespace(
            register_web_api=lambda route, handler, methods, description: registered.append((route, methods))
        )
    )
    PluginPageApi(plugin=plugin).register_routes()

    assert (f"{PAGE_API_PREFIX}/graphs/social/groups", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/graphs/social", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/graphs/social/action", ["POST"]) in registered


def test_social_groups_reuse_social_service():
    api = _make_api()

    result = asyncio.run(api.get_social_groups())

    assert result["status"] == "ok"
    assert result["data"]["total"] == 1
    assert result["data"]["groups"][0]["group_id"] == "g1"
    assert _FakeSocialService.calls == [("groups",)]


def test_social_groups_failure_is_soft_operation():
    api = _make_api()
    _FakeSocialService.fail = True

    result = asyncio.run(api.get_social_groups())

    assert result["data"]["success"] is False
    assert result["data"]["message"] == "请求处理失败，请稍后重试"


def test_social_relations_forward_group_id_and_require_it():
    api = _make_api(query={"group_id": "g1"})
    result = asyncio.run(api.get_social_relations())

    assert result["data"]["member_count"] == 1
    assert result["data"]["relations"][0]["strength"] == 0.8
    assert _FakeSocialService.calls == [("relations", "g1")]

    api = _make_api(query={})
    result = asyncio.run(api.get_social_relations())
    assert result["data"]["success"] is False
    assert _FakeSocialService.calls == []


def test_social_analyze_action_wraps_service_result():
    api = _make_api(body={"action": "analyze", "group_id": "g1"})

    result = asyncio.run(api.post_social_action())

    assert result["data"]["success"] is True
    assert "分析已完成" in result["data"]["message"]
    assert _FakeSocialService.calls == [("analyze", "g1")]


def test_social_clear_action_requires_page_confirmation():
    api = _make_api(body={"action": "clear", "group_id": "g1"})
    result = asyncio.run(api.post_social_action())
    assert result["data"]["success"] is False
    assert _FakeSocialService.calls == []

    api = _make_api(body={"action": "clear", "group_id": "g1", "confirmed": True})
    result = asyncio.run(api.post_social_action())
    assert result["data"]["success"] is True
    assert _FakeSocialService.calls == [("clear", "g1")]


def test_social_share_action_points_to_standalone_webui():
    api = _make_api(body={"action": "share", "group_id": "g1", "expires_hours": 168})

    result = asyncio.run(api.post_social_action())

    data = result["data"]["data"]
    assert result["data"]["success"] is True
    assert data["share_path"] == "/graph/share/tok_abcdefghijklmnopqrstuvwxyz"
    assert data["share_url"] == "http://127.0.0.1:7833/graph/share/tok_abcdefghijklmnopqrstuvwxyz"
    assert data["expires_at"] == "2026-11-14T00:00:00Z"
    assert _FakeGraphShareService.calls == [("g1", 168)]


def test_social_share_action_without_webui_has_no_url_and_validates_hours():
    api = _make_api(body={"action": "share", "group_id": "g1"}, webui_enabled=False)
    result = asyncio.run(api.post_social_action())
    assert result["data"]["success"] is True
    assert result["data"]["data"]["share_url"] is None

    api = _make_api(body={"action": "share", "group_id": "g1", "expires_hours": 9999})
    result = asyncio.run(api.post_social_action())
    assert result["data"]["success"] is False
    assert _FakeGraphShareService.calls == []


def test_social_action_rejects_missing_group_and_unknown_action():
    api = _make_api(body={"action": "analyze"})
    assert asyncio.run(api.post_social_action())["data"]["success"] is False

    api = _make_api(body={"action": "explode", "group_id": "g1"})
    result = asyncio.run(api.post_social_action())
    assert result["data"]["success"] is False
    assert "未知社交关系操作" in result["data"]["message"]
