"""回归测试：内嵌插件页影子模式与世界书导入端点。

影子模式与世界书原为独立 WebUI 专属功能，迁移到 ``pages/dashboard`` 后经
``page/shadow-mode*`` 与 ``page/integrations/action`` 暴露；此处锁定参数
透传与失败路径，防止后续改动破坏内嵌页入口。
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


class _FakeShadowService:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def get_status(self) -> dict:
        self.calls.append(("get_status", {}))
        return {
            "sources": {"live": [{"group_id": "g1", "member_count": 5}], "imported": []},
            "profiles": [],
            "minimum_samples": 3,
        }

    async def list_candidates(self, *, source_type: str, group_id: str) -> dict:
        self.calls.append(("list_candidates", {"source_type": source_type, "group_id": group_id}))
        return {"candidates": [{"sender_id": "u1", "sender_name": "甲", "ready": True}], "minimum_samples": 3}

    async def learn(self, **kwargs) -> dict:
        self.calls.append(("learn", kwargs))
        return {"id": 1, "enabled": True, **kwargs}

    async def set_enabled(self, profile_id: int, enabled: bool) -> dict:
        self.calls.append(("set_enabled", {"profile_id": profile_id, "enabled": enabled}))
        return {"id": profile_id, "enabled": enabled}


class _FakeWorldbookImporter:
    instances: list["_FakeWorldbookImporter"] = []

    def __init__(self, database_manager=None):
        self.database_manager = database_manager
        self.preview_calls: list[dict] = []
        self.import_calls: list[dict] = []
        self.history_calls: list[dict] = []
        _FakeWorldbookImporter.instances.append(self)

    def preview(self, **kwargs) -> dict:
        self.preview_calls.append(kwargs)
        return {"counts": {"entries": 2}, "review_breakdown": {"jargon_candidates": 4}}

    async def import_from_source(self, **kwargs) -> dict:
        self.import_calls.append(kwargs)
        return {"success": True, "entries_imported": 2}

    async def import_history(self, *, limit: int, offset: int) -> dict:
        self.history_calls.append({"limit": limit, "offset": offset})
        return {"imports": {}}


def _make_api(*, body: dict, query: dict | None = None) -> tuple[PluginPageApi, _FakeShadowService]:
    shadow = _FakeShadowService()
    container = SimpleNamespace(database_manager=object())

    def fake_imports():
        return SimpleNamespace(
            ShadowModeService=lambda database_manager: shadow,
            WorldBookImporter=_FakeWorldbookImporter,
            MaiBotLearningImporter=lambda database_manager: None,
            QQChatHistoryImporter=lambda database_manager: None,
        )

    api = PluginPageApi(plugin=SimpleNamespace())
    api._imports = fake_imports
    api._container = lambda: container

    async def fake_body() -> dict:
        return body

    api._body = fake_body
    if query is not None:
        api._query = lambda: query
    return api, shadow


def test_get_shadow_mode_status():
    api, shadow = _make_api(body={}, query={})
    result = asyncio.run(api.get_shadow_mode())

    assert result["status"] == "ok"
    assert result["data"]["sources"]["live"][0]["group_id"] == "g1"
    assert shadow.calls[0][0] == "get_status"


def test_get_shadow_mode_candidates_passes_query():
    api, shadow = _make_api(body={}, query={"source": "imported", "group_id": "g2"})
    result = asyncio.run(api.get_shadow_mode_candidates())

    assert result["status"] == "ok"
    assert result["data"]["candidates"][0]["sender_id"] == "u1"
    assert shadow.calls == [("list_candidates", {"source_type": "imported", "group_id": "g2"})]


def test_get_shadow_mode_candidates_value_error_is_soft_failure():
    api, _ = _make_api(body={}, query={})

    async def boom(**kwargs):
        raise ValueError("bad source")

    api._shadow_service = lambda: SimpleNamespace(list_candidates=boom)
    result = asyncio.run(api.get_shadow_mode_candidates())

    assert result["data"]["success"] is False


def test_post_shadow_mode_action_learn():
    api, shadow = _make_api(
        body={
            "action": "learn",
            "source_type": "live",
            "source_group_id": "g1",
            "target_group_id": "g9",
            "sender_id": "u1",
            "activate": True,
        }
    )
    result = asyncio.run(api.post_shadow_mode_action())

    assert result["data"]["success"] is True
    assert result["data"]["profile"]["target_group_id"] == "g9"
    assert shadow.calls == [("learn", {
        "source_type": "live",
        "source_group_id": "g1",
        "target_group_id": "g9",
        "sender_id": "u1",
        "activate": True,
    })]


def test_post_shadow_mode_action_set_enabled():
    api, shadow = _make_api(body={"action": "set_enabled", "profile_id": "7", "enabled": False})
    result = asyncio.run(api.post_shadow_mode_action())

    assert result["data"]["success"] is True
    assert shadow.calls == [("set_enabled", {"profile_id": 7, "enabled": False})]


def test_post_shadow_mode_action_learn_value_error_surfaces_message():
    api, _ = _make_api(body={"action": "learn", "sender_id": "u1"})

    async def reject(**kwargs):
        raise ValueError("样本不足，无法学习该用户")

    api._shadow_service = lambda: SimpleNamespace(learn=reject)
    result = asyncio.run(api.post_shadow_mode_action())

    assert result["data"]["success"] is False
    assert "样本不足" in result["data"]["message"]


def test_post_shadow_mode_action_unknown():
    api, shadow = _make_api(body={"action": "nope"})
    result = asyncio.run(api.post_shadow_mode_action())

    assert result["data"]["success"] is False
    assert "未知影子模式操作" in result["data"]["message"]
    assert shadow.calls == []


def test_post_integrations_action_worldbook_preview_never_receives_path():
    api, _ = _make_api(body={"action": "worldbook_preview", "payload": {"entries": [1]}, "json_path": "/etc/passwd"})
    _FakeWorldbookImporter.instances = []
    result = asyncio.run(api.post_integrations_action())

    assert result["data"]["success"] is True
    importer = _FakeWorldbookImporter.instances[-1]
    assert importer.preview_calls[0]["payload"] == {"entries": [1]}
    # 出于安全考虑，内嵌页与独立 WebUI 一样不接受服务器端路径。
    assert importer.preview_calls[0]["json_path"] is None


def test_post_integrations_action_worldbook_import_flags():
    api, _ = _make_api(
        body={
            "action": "worldbook_import",
            "json_text": "{}",
            "default_group_id": "g3",
            "import_memories": False,
            "import_jargons": True,
            "import_knowledge_graph": False,
            "include_disabled": True,
        }
    )
    _FakeWorldbookImporter.instances = []
    result = asyncio.run(api.post_integrations_action())

    assert result["data"]["success"] is True
    call = _FakeWorldbookImporter.instances[-1].import_calls[0]
    assert call["default_group_id"] == "g3"
    assert call["import_memories"] is False
    assert call["import_jargons"] is True
    assert call["import_knowledge_graph"] is False
    assert call["include_disabled"] is True
    assert call["json_path"] is None


def test_post_integrations_action_worldbook_history_bounds_limit():
    api, _ = _make_api(body={"action": "worldbook_history", "limit": 500})
    _FakeWorldbookImporter.instances = []
    result = asyncio.run(api.post_integrations_action())

    assert result["data"]["success"] is True
    assert _FakeWorldbookImporter.instances[-1].history_calls == [{"limit": 50, "offset": 0}]


def test_post_integrations_action_worldbook_invalid_json_reports_failure():
    api, _ = _make_api(body={"action": "worldbook_preview", "payload": {"entries": []}})

    def broken_preview(**kwargs):
        raise ValueError("世界书 JSON 格式无效")

    _FakeWorldbookImporter.instances = []
    # 还原类方法而不是 del：pytest-randomly 会打乱用例顺序，删除类属性会
    # 污染后续依赖 preview 的用例（CI 随机失败的根因）。
    original_preview = _FakeWorldbookImporter.preview
    _FakeWorldbookImporter.preview = broken_preview
    try:
        result = asyncio.run(api.post_integrations_action())
    finally:
        _FakeWorldbookImporter.preview = original_preview

    assert result["data"]["success"] is False
