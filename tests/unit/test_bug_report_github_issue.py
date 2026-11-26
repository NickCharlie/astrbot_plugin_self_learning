"""Bug 反馈改为 GitHub issue 预填链接后的回归测试。

覆盖三件事：
1. 生成的链接指向仓库的 issue 模板，且按模板字段 id 预填（模板与代码不一致会立刻失败）；
2. 必填项缺失时不生成链接；
3. 不再对外发起任何网络请求（历史实现会 POST 到禅道云函数）。
"""

import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from webui.services.bug_report_service import BugReportService

TEMPLATE = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"


def _service(**webui_overrides) -> BugReportService:
    defaults = {
        "bug_report_enabled": True,
        "bug_report_repository": "NickCharlie/astrbot_plugin_self_learning",
    }
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(version="4.9.8", db_type="sqlite"),
        webui_config=SimpleNamespace(**{**defaults, **webui_overrides}),
    )
    return BugReportService(container)


def _template_field_ids() -> set[str]:
    """从模板读回所有元素 id，作为预填键的唯一事实来源。"""
    text = TEMPLATE.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*id:\s*(\S+)\s*$", text, re.MULTILINE))


def test_issue_url_prefills_only_ids_declared_by_the_template():
    url = _service().build_issue_url(
        {
            "title": "影子档案删不掉",
            "steps": "1. 打开影子模式\n2. 点击删除",
            "severity": 2,
            "pri": 1,
            "type": "codeerror",
            "build": "4.9.8",
            "os": "Windows",
            "mailto": "a@b.c",
        }
    )

    parsed = urlparse(url)
    assert parsed.path == "/NickCharlie/astrbot_plugin_self_learning/issues/new"
    query = parse_qs(parsed.query)
    assert query["template"] == ["bug_report.yml"]
    # title 是 GitHub 的通用查询参数（不是表单元素 id）；其余键都必须由模板声明，
    # 否则预填会被 GitHub 静默丢弃
    allowed_generic = {"template", "title"}
    assert set(query) - allowed_generic <= _template_field_ids()
    assert query["template"] == ["bug_report.yml"]
    assert "severity" in query and "priority" in query and "contact" in query
    assert query["version"] == ["4.9.8"]
    assert query["title"] == ["影子档案删不掉"]
    assert "【优先级】1 - 紧急" in query["steps"][0]


def test_required_fields_reject_before_building_a_link():
    service = _service()

    ok, message, data = pytest.importorskip("asyncio").run(
        service.submit_bug_report({"title": "", "steps": "1. 复现"})
    )

    assert ok is False
    assert "title" in message
    assert data is None


def test_submit_returns_link_without_network_io(monkeypatch):
    import aiohttp

    def _boom(*args, **kwargs):
        raise AssertionError("Bug 反馈不应再访问网络（云函数已欠费停用）")

    monkeypatch.setattr(aiohttp.ClientSession, "__init__", _boom)
    service = _service()

    ok, message, data = pytest.importorskip("asyncio").run(
        service.submit_bug_report({"title": "标题", "steps": "1. 复现"})
    )

    assert ok is True
    assert data["repository"] == "NickCharlie/astrbot_plugin_self_learning"
    assert data["url"].startswith("https://github.com/NickCharlie/astrbot_plugin_self_learning/issues/new?")
    assert "GitHub" in message


def test_config_exposes_repository_and_defaults():
    config = _service(bug_report_enabled=False).get_bug_report_config()

    assert config["mode"] == "github_issue"
    assert config["template"] == "bug_report.yml"
    assert config["repository"] == "NickCharlie/astrbot_plugin_self_learning"
    assert config["defaultBuild"] == "4.9.8"
    assert config["enabled"] is False
    assert config["newIssueUrl"].endswith("/issues/new")
    # 模板下拉项必须能由面板选项拼出，否则预填会被 GitHub 丢弃
    for key in ("severityOptions", "priorityOptions", "typeOptions", "dbTypeOptions", "osOptions"):
        assert config[key], key