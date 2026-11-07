"""回归测试：内嵌插件页情绪中枢桥接路由（与独立 WebUI /api/emotion/* 同源逻辑）。

内嵌页此前缺少情绪中枢分区，且 page_api 未暴露 emotion 路由——内嵌页只能通过
AstrBot 插件页桥接访问 ``page/*``，无法调用独立 WebUI 的 Quart 蓝图。本组用例
锁定三条桥接路由的注册与行为：读板块、读走向（days 参数）、执行治理动作。
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


class _FakeEmotionService:
    """记录调用的情绪板块服务替身。"""

    calls: list = []

    def __init__(self, container):
        self.container = container

    async def get_board(self):
        _FakeEmotionService.calls.append(("board", self.container))
        return {"available": True, "moods": {"active": [], "history": []}}

    async def get_trends(self, days):
        _FakeEmotionService.calls.append(("trends", days))
        return {"days": days, "affection_delta": [], "mood_changes": [], "gate": []}

    async def run_action(self, body):
        _FakeEmotionService.calls.append(("action", body))
        if body.get("action") == "boom":
            raise RuntimeError("service exploded")
        return {"success": True, "message": "心情已设置", "group_id": body.get("group_id")}


def _make_api(query=None, body=None) -> PluginPageApi:
    api = PluginPageApi(plugin=SimpleNamespace())
    container = SimpleNamespace(bound=True)
    api._imports = lambda: SimpleNamespace(
        get_container=lambda: container,
        EmotionBoardService=_FakeEmotionService,
    )
    api._query = lambda: query or {}

    async def _body():
        return body or {}

    api._body = _body
    _FakeEmotionService.calls = []
    return api


def test_emotion_routes_registered_on_bridge():
    registered = []
    plugin = SimpleNamespace(
        context=SimpleNamespace(
            register_web_api=lambda route, handler, methods, description: registered.append((route, methods))
        )
    )
    PluginPageApi(plugin=plugin).register_routes()

    assert (f"{PAGE_API_PREFIX}/emotion/board", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/emotion/trends", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/emotion/action", ["POST"]) in registered


def test_emotion_board_returns_service_payload():
    api = _make_api()

    result = asyncio.run(api.get_emotion_board())

    assert result["status"] == "ok"
    assert result["data"]["available"] is True
    assert _FakeEmotionService.calls[0][0] == "board"


def test_emotion_trends_forwards_days_param_with_default():
    api = _make_api(query={"days": "30"})
    result = asyncio.run(api.get_emotion_trends())
    assert result["data"]["days"] == 30

    api = _make_api(query={})
    result = asyncio.run(api.get_emotion_trends())
    assert result["data"]["days"] == 14


def test_emotion_action_wraps_service_result_as_operation():
    api = _make_api(body={"action": "set_mood", "group_id": "g1", "mood_type": "happy"})

    result = asyncio.run(api.post_emotion_action())

    assert result["status"] == "ok"
    assert result["data"]["success"] is True
    assert result["data"]["message"] == "心情已设置"
    assert result["data"]["group_id"] == "g1"
    assert _FakeEmotionService.calls[0] == ("action", {"action": "set_mood", "group_id": "g1", "mood_type": "happy"})


def test_emotion_action_failure_reports_unsuccessful_operation():
    api = _make_api(body={"action": "boom"})

    result = asyncio.run(api.post_emotion_action())

    assert result["data"]["success"] is False
    assert "service exploded" in result["data"]["message"]
