"""回归测试：内嵌插件页审查队列「最近学习批次」、人格学习页与表达学习页的桥接路由。

审查队列的「最近学习批次」（分页、重跑学习、删除批次）、人格学习页的待审更新 /
最近已审查 / 全部群组备份 / 人格详情，以及表达学习页的表达样本库，在独立 WebUI 中
由 /api/batches、/api/relearn、/api/persona_updates*、/api/persona_backups/list、
/api/persona_management/get、/api/style_learning/content_text 提供。内嵌页只能经
``page/*`` 桥接访问，本组用例锁定桥接复用同一组服务方法、口径与独立版一致。
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


class _FakeContentService:
    calls: list = []
    fail = False

    def __init__(self, container):
        self.container = container

    async def list_batches(self, page, page_size):
        _FakeContentService.calls.append(("list_batches", page, page_size))
        if _FakeContentService.fail:
            raise RuntimeError("batch table unavailable")
        return {
            "batches": [{"id": 7, "batch_name": "首次学习", "group_id": "g1", "quality_score": 0.88}],
            "total": 11,
            "page": page,
            "page_size": page_size,
            "total_pages": 2,
        }

    async def get_content_text(self):
        _FakeContentService.calls.append(("content_text",))
        return {"dialogues": [{"id": 1, "title": "Alice"}], "analysis": [], "features": [], "history": []}


class _FakeTrendsDatabase:
    async def get_trends_data(self):
        return {"daily_messages": {}, "recent_batches": [{"id": 3, "batch_name": "趋势批次"}]}


class _FakeLearningService:
    calls: list = []

    def __init__(self, container):
        self.container = container

    async def get_style_learning_results(self):
        return {"statistics": {"total_samples": 4}, "style_progress": []}

    async def get_style_learning_patterns(self):
        return {"emotion_patterns": [{"name": "开心"}], "language_patterns": [], "topic_patterns": []}

    async def update_style_learning_review(self, review_id, payload):
        _FakeLearningService.calls.append((review_id, payload))
        return True, "表达方式已更新", {"id": review_id}


class _FakePersonaService:
    def __init__(self, container):
        self.container = container

    async def get_all_personas(self):
        return [{"persona_id": "p1", "name": "测试人格"}]

    async def get_current_persona_state(self, group_id):
        return {"group_id": group_id, "persona": {"name": "当前人格"}, "prompt_length": 3}

    async def get_default_persona(self, group_id):
        return {"persona_id": "default", "system_prompt": "", "begin_dialogs": []}

    async def get_persona_details(self, persona_id):
        if persona_id == "missing":
            return None
        return {"persona_id": persona_id, "system_prompt": "人格提示词", "begin_dialogs": [], "tools": []}


class _FakeBackupService:
    calls: list = []

    def __init__(self, container):
        self.container = container

    async def list_backups(self, group_id=None, limit=20):
        _FakeBackupService.calls.append((group_id, limit))
        return {"backups": [{"id": 3, "backup_name": "备份A"}], "total": 1, "available": True}


class _FakeReviewService:
    calls: list = []

    def __init__(self, container):
        self.container = container

    async def get_pending_persona_updates(self, limit=0, offset=0, keyword=""):
        _FakeReviewService.calls.append(("pending", limit))
        return {"success": True, "updates": [{"id": 1, "review_source": "traditional"}], "total": 1}

    async def get_reviewed_persona_updates(self, limit=50, offset=0, status_filter=None):
        _FakeReviewService.calls.append(("reviewed", limit, offset, status_filter))
        return {"success": True, "updates": [{"id": "persona_learning_2", "status": "approved"}], "total": 1}


def _make_api(query=None, body=None, container=None) -> PluginPageApi:
    api = PluginPageApi(plugin=SimpleNamespace())
    bound = container or SimpleNamespace(bound=True, database_manager=None)
    api._imports = lambda: SimpleNamespace(
        get_container=lambda: bound,
        LearningContentService=_FakeContentService,
        LearningService=_FakeLearningService,
        PersonaService=_FakePersonaService,
        PersonaBackupService=_FakeBackupService,
        PersonaReviewService=_FakeReviewService,
    )
    api._query = lambda: query or {}

    async def _body():
        return body or {}

    api._body = _body
    _FakeContentService.calls = []
    _FakeContentService.fail = False
    _FakeLearningService.calls = []
    _FakeBackupService.calls = []
    _FakeReviewService.calls = []
    return api


def test_batch_routes_registered_on_bridge():
    registered = []
    plugin = SimpleNamespace(
        context=SimpleNamespace(
            register_web_api=lambda route, handler, methods, description: registered.append((route, methods))
        )
    )
    PluginPageApi(plugin=plugin).register_routes()

    assert (f"{PAGE_API_PREFIX}/batches", ["GET"]) in registered
    assert (f"{PAGE_API_PREFIX}/batches/action", ["POST"]) in registered


def test_get_batches_uses_shared_service_with_standalone_page_size():
    api = _make_api(query={"page": "2"})

    result = asyncio.run(api.get_batches())

    assert result["status"] == "ok"
    # 与独立 WebUI 审查队列一致：每页 10 条
    assert _FakeContentService.calls == [("list_batches", 2, 10)]
    assert result["data"]["total_pages"] == 2
    assert result["data"]["batches"][0]["batch_name"] == "首次学习"


def test_get_batches_falls_back_to_recent_trend_batches():
    api = _make_api(container=SimpleNamespace(bound=True, database_manager=_FakeTrendsDatabase()))
    _FakeContentService.fail = True

    result = asyncio.run(api.get_batches())

    assert result["data"]["batches"] == [{"id": 3, "batch_name": "趋势批次"}]
    assert result["data"]["total_pages"] == 1


def test_batch_relearn_requires_group_and_reuses_relearn():
    calls = []
    api = _make_api(body={"action": "relearn", "group_id": "g1"})

    async def _relearn(group_id):
        calls.append(group_id)
        return {"success": True, "message": f"重新学习已启动，群组: {group_id}"}

    api._relearn = _relearn
    result = asyncio.run(api.post_batches_action())
    assert result["data"]["success"] is True
    assert calls == ["g1"]

    api = _make_api(body={"action": "relearn", "group_id": ""})
    api._relearn = _relearn
    result = asyncio.run(api.post_batches_action())
    assert result["data"]["success"] is False
    assert calls == ["g1"]


def test_batch_relearn_all_auto_detects_busiest_group_without_batches():
    """全局重新学习不依赖批次存在：交给 _relearn("default") 自动选择消息最多的群组。"""
    calls = []
    api = _make_api(body={"action": "relearn_all"})

    async def _relearn(group_id):
        calls.append(group_id)
        return {"success": True, "message": "重新学习已启动，群组: busiest", "group_id": "busiest"}

    api._relearn = _relearn
    result = asyncio.run(api.post_batches_action())

    assert calls == ["default"]
    assert result["data"]["success"] is True
    assert result["data"]["message"] == "重新学习已启动，群组: busiest"


def test_batch_delete_reuses_batch_deletion():
    deleted = []
    api = _make_api(body={"action": "delete", "id": "7"})

    async def _delete(batch_id):
        deleted.append(batch_id)
        return True, f"学习批次 {batch_id} 已删除"

    api._delete_learning_batch = _delete
    result = asyncio.run(api.post_batches_action())

    assert result["data"]["success"] is True
    assert deleted == [7]

    api = _make_api(body={"action": "explode"})
    result = asyncio.run(api.post_batches_action())
    assert result["data"]["success"] is False
    assert "未知学习批次操作" in result["data"]["message"]


def test_persona_payload_matches_standalone_sources():
    api = _make_api(query={})

    result = asyncio.run(api.get_persona())
    data = result["data"]

    # 备份：全部群组最近 8 条（/api/persona_backups/list?limit=8）
    assert _FakeBackupService.calls == [(None, 8)]
    # 待审首屏 10 条、已审查 5 条（/api/persona_updates?limit=10、/reviewed?limit=5）
    assert ("pending", 10) in _FakeReviewService.calls
    assert ("reviewed", 5, 0, None) in _FakeReviewService.calls
    assert data["pending"]["updates"][0]["id"] == 1
    assert data["reviewed"]["updates"][0]["status"] == "approved"
    assert data["current"]["group_id"] == "default"
    assert data["errors"] == {}


def test_persona_get_action_reads_details():
    api = _make_api(body={"action": "get", "persona_id": "p1"})
    result = asyncio.run(api.post_persona_action())
    assert result["data"]["success"] is True
    assert result["data"]["persona"]["system_prompt"] == "人格提示词"

    api = _make_api(body={"action": "get", "persona_id": "missing"})
    result = asyncio.run(api.post_persona_action())
    assert result["data"]["success"] is False


def test_style_payload_includes_sample_library_content():
    api = _make_api()

    result = asyncio.run(api.get_style())
    data = result["data"]

    assert data["results"]["statistics"]["total_samples"] == 4
    assert data["patterns"]["emotion_patterns"][0]["name"] == "开心"
    assert data["content"]["dialogues"][0]["title"] == "Alice"
    # 待审表达统一在审查队列处理，表达学习页不再拉取审查列表
    assert "reviews" not in data


def test_style_update_delegates_to_learning_service():
    api = _make_api(body={"action": "update", "id": "5", "description": "新的描述"})

    result = asyncio.run(api.post_style_action())

    assert result["data"]["success"] is True
    assert result["data"]["message"] == "表达方式已更新"
    review_id, payload = _FakeLearningService.calls[0]
    assert review_id == 5
    assert payload["description"] == "新的描述"
