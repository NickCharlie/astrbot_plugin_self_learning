"""回归测试：内嵌插件页 dashboard 聚合与独立 WebUI 同口径（首页 / AI 巡检 / 运行监控）。

独立 WebUI 的首页「学习效率 / 待办总量 / 内容样本」、运行监控「模型调用」与巡检
「模型异常」读 ``/api/metrics`` 与 ``/api/data/statistics``；内嵌页只能经桥接读
``page/dashboard``，过去缺少这些字段，只能显示 0 或改用另一套口径。本组用例锁定：

- ``page/dashboard`` 的 ``metrics`` 段带上与 ``/api/metrics`` 相同的顶层字段，
  且由与蓝图共用的同一组函数计算；
- ``page/dashboard`` 新增 ``data_statistics`` 段（读取失败计入 errors）；
- 首页不再下发宿主链接（其中「插件设置」在 iframe 内是死链 ``#/extension``）。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.page_api import PluginPageApi  # noqa: E402
from self_learning_EterU.webui.services.metrics_service import (  # noqa: E402
    compute_learning_efficiency,
    summarize_llm_call_statistics,
)


class _FakeDatabase:
    async def get_messages_statistics(self):
        return {"total_messages": 120, "filtered_messages": 30}

    async def get_trends_data(self):
        return {"daily_messages": {"2026-11-06": 3}, "recent_batches": [{"id": 1}, {"id": 2}]}

    async def get_style_learning_statistics(self):
        return {"approved_reviews": 4, "total_reviews": 9}

    async def get_expression_patterns_statistics(self):
        return {"total_patterns": 13}

    async def get_learning_performance_history(self, group_id):
        return [
            {"quality_score": 0.9, "success": True},
            {"quality_score": 0.0, "success": False},
            {"quality_score": 0.5, "success": True},
        ]


class _FakeLlmAdapter:
    def get_call_statistics(self):
        return {
            "overall": {"total_calls": 49},
            "filter": {"total_calls": 40, "avg_response_time_ms": 120.456, "success_rate": 0.97, "error_count": 1},
            "refine": {"total_calls": 6, "avg_response_time_ms": 300, "success_rate": 1.0, "error_count": 0},
            "chat": {"total_calls": 3},
            "reinforce": {"total_calls": 0},
        }

    def get_provider_info(self):
        return {"filter": "FilterModel", "refine": "RefineModel"}


class _FakeMetricsService:
    def __init__(self, container):
        self.container = container

    async def get_intelligence_metrics(self, group_id):
        return {"overall_score": 45.5, "dimensions": {"a": 1, "b": 2}, "trends": []}

    async def get_diversity_metrics(self, group_id):
        return {"total_score": 0}

    async def get_affection_metrics(self, group_id):
        return {"total_users": 0}


class _FakeDataManagementService:
    calls = 0
    fail = False

    def __init__(self, container):
        self.container = container

    async def get_data_statistics(self):
        _FakeDataManagementService.calls += 1
        if _FakeDataManagementService.fail:
            raise ValueError("数据库管理器未初始化")
        return {"style_learning": 7, "memory": 3, "knowledge_graph": 2}


def _make_api(container) -> PluginPageApi:
    api = PluginPageApi(plugin=SimpleNamespace())
    api._imports = lambda: SimpleNamespace(
        get_container=lambda: container,
        MetricsService=_FakeMetricsService,
        DataManagementService=_FakeDataManagementService,
        compute_learning_efficiency=compute_learning_efficiency,
        summarize_llm_call_statistics=summarize_llm_call_statistics,
    )
    return api


def _container(**overrides):
    values = dict(
        bound=True,
        database_manager=_FakeDatabase(),
        llm_adapter=_FakeLlmAdapter(),
        progressive_learning=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_load_metrics_exposes_standalone_metrics_fields():
    api = _make_api(_container())

    metrics = asyncio.run(api._load_metrics())

    # 与 /api/metrics 同源：消息统计、学习效率四项加权（25 + 40 + 26 + 70）/ 4 = 40.2
    assert metrics["total_messages_collected"] == 120
    assert metrics["filtered_messages"] == 30
    assert metrics["learning_efficiency"] == 40.2
    assert metrics["learning_dimensions"]["filter_rate"] == 25.0
    assert metrics["learning_dimensions"]["total_sessions"] == 3

    # 模型调用：0 次的 Provider 被过滤，调用量 ≥ max(5, 均值 × 1.5) 记为异常
    summary = metrics["llm_call_summary"]
    assert summary["total_calls"] == 49
    assert summary["provider_count"] == 3
    assert summary["abnormal_provider_count"] == 1
    breakdown = metrics["llm_call_breakdown"]
    assert [row["provider_type"] for row in breakdown] == ["filter", "refine", "chat"]
    assert breakdown[0]["provider_label"] == "FilterModel"
    assert breakdown[0]["is_abnormal"] is True
    assert breakdown[1]["is_abnormal"] is False
    assert metrics["filter_model_summary"]["configured"] is True
    assert set(metrics["llm_calls"]) == {"filter_provider", "refine_provider", "chat_provider"}

    # 原有字段保留，system_metrics 与 system 同一份读数
    assert metrics["trends"]["recent_batches"] == [{"id": 1}, {"id": 2}]
    assert metrics["intelligence"]["overall_score"] == 45.5
    assert metrics["system_metrics"] is metrics["system"]
    assert "memory_percent" in metrics["system_metrics"]


def test_load_metrics_without_database_or_llm_falls_back_to_zero():
    api = _make_api(_container(database_manager=None, llm_adapter=None))

    metrics = asyncio.run(api._load_metrics())

    assert metrics["total_messages_collected"] == 0
    assert metrics["learning_efficiency"] == 0
    assert metrics["learning_dimensions"] == {}
    assert metrics["llm_call_breakdown"] == []
    assert metrics["llm_call_summary"]["total_calls"] == 0
    assert metrics["llm_call_summary"]["abnormal_provider_count"] == 0


def test_dashboard_includes_data_statistics_and_records_failures():
    api = _make_api(_container())

    async def _section(value):
        return value

    review_limits = []

    async def _reviews(limit=50, **_):
        review_limits.append(limit)
        return {"persona_pending": {"updates": [], "total": 0}}

    api._load_overview = lambda: _section({"errors": {}})
    api._load_reviews = _reviews
    api._load_content = lambda **_: _section({})
    api._load_metrics = lambda: _section({})
    api._load_monitoring = lambda: _section({})
    api._load_integrations = lambda: _section({})
    api._load_graphs = lambda **_: _section({})
    api._load_settings = lambda **_: _section({})

    _FakeDataManagementService.fail = False
    result = asyncio.run(api.get_dashboard())
    assert result["status"] == "ok"
    assert result["data"]["data_statistics"] == {"style_learning": 7, "memory": 3, "knowledge_graph": 2}
    assert "data_statistics" not in result["data"]["errors"]
    # 人格待审首页与独立 WebUI 一样取首屏 10 条判断是否混入风格审查
    assert review_limits == [10]

    _FakeDataManagementService.fail = True
    try:
        result = asyncio.run(api.get_dashboard())
    finally:
        _FakeDataManagementService.fail = False
    assert result["data"]["data_statistics"] == {}
    assert result["data"]["errors"]["data_statistics"] == "数据库管理器未初始化"


class _AnyService:
    """任意方法都返回空字典的服务替身（只关心 overview 的结构）。"""

    def __init__(self, container):
        self.container = container

    def __getattr__(self, name):
        async def _method(*args, **kwargs):
            return {}

        return _method


def test_overview_no_longer_ships_host_quick_links_or_modules():
    api = _make_api(_container())
    imports = api._imports()
    for name in ("JargonService", "LearningService", "PersonaService", "PersonaBackupService", "MetricsService"):
        setattr(imports, name, _AnyService)
    api._imports = lambda: imports

    overview = asyncio.run(api._load_overview())

    # 首页模块卡 / 快捷入口改由前端静态定义（与独立 WebUI HomePage 一致）
    assert "quick_links" not in overview
    assert "modules" not in overview
    assert overview["runtime"]["database_ready"] is True
    assert "dashboard_url" in overview["webui"]
    assert not hasattr(PluginPageApi, "_build_quick_links")
    assert not hasattr(PluginPageApi, "_build_modules")
