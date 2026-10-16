"""回归测试：内嵌插件页 jargon/action 的 import_jargons 分支（issue #269）。

issue #269：pages/dashboard 导入按钮把 ``action: "import_jargons"`` 发往
``jargon/action``，但 ``post_jargon_action`` 缺少该分支，落入
"未知黑话操作" 兜底；可用的实现只在 ``post_reviews_action`` 里。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.page_api import PluginPageApi


class _FakeJargonService:
    instances: list["_FakeJargonService"] = []

    def __init__(self, container):
        self.container = container
        self.import_calls: list[dict] = []

    async def import_jargons(self, payload: dict) -> dict:
        self.import_calls.append(payload)
        return {"success": True, "message": f"导入 {len(payload['text'].splitlines())} 条"}


def _make_api() -> tuple[PluginPageApi, _FakeJargonService]:
    service = _FakeJargonService(container=object())
    _FakeJargonService.instances = [service]

    def fake_imports():
        return SimpleNamespace(JargonService=lambda container: service)

    api = PluginPageApi(plugin=SimpleNamespace())
    api._imports = fake_imports
    api._container = lambda: service.container

    async def fake_body() -> dict:
        return {
            "action": "import_jargons",
            "text": "awsl = 一种兴奋的表达\nyyds = 表示赞叹",
            "group_id": "",
            "is_global": True,
        }

    api._body = fake_body
    return api, service


def test_post_jargon_action_handles_import_jargons():
    api, service = _make_api()
    result = asyncio.run(api.post_jargon_action())

    assert result["status"] == "ok"
    assert result["data"]["success"] is True
    assert "导入" in result["data"]["message"]
    assert len(service.import_calls) == 1
    payload = service.import_calls[0]
    assert payload["text"].startswith("awsl")
    assert payload["group_id"] == ""
    # is_global 原样透传，由 service 严格解析
    assert payload["is_global"] is True


def test_post_jargon_action_import_failure_propagates_message():
    api, service = _make_api()

    async def failing_import(payload: dict) -> dict:
        return {"success": False, "error": "群组ID包含非法字符"}

    service.import_jargons = failing_import
    result = asyncio.run(api.post_jargon_action())

    assert result["status"] == "ok"
    assert result["data"]["success"] is False
    assert result["data"]["message"] == "群组ID包含非法字符"


def test_post_jargon_action_partial_failure_reports_as_failed():
    # Sourcery 意见：部分行失败时前端必须按失败处理（保留输入框供重试），
    # 不能因 success:true 而清空用户已输入的文本。
    api, service = _make_api()

    async def partial_import(payload: dict) -> dict:
        return {
            "success": True,
            "message": "导入完成：新增 1 条，候选升级 0 条，跳过重复 0 条，失败 1 条",
            "details": {
                "imported": 1,
                "updated": 0,
                "skipped": 0,
                "failed": [{"line": 2, "term": "x" * 64, "reason": "写入失败"}],
                "total": 2,
            },
        }

    service.import_jargons = partial_import
    result = asyncio.run(api.post_jargon_action())

    assert result["data"]["success"] is False
    assert "失败 1 条" in result["data"]["message"]
    assert result["data"]["result"]["details"]["imported"] == 1


def test_post_jargon_action_unknown_action_still_rejected():
    api, service = _make_api()

    async def body_without_action() -> dict:
        return {"action": "definitely_not_supported"}

    api._body = body_without_action
    result = asyncio.run(api.post_jargon_action())

    assert result["data"]["success"] is False
    assert "未知黑话操作" in result["data"]["message"]
    assert service.import_calls == []
