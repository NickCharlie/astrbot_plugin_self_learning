"""Regression tests for bundled WebUI frontend assets."""

from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HTML_FILES = [
    PLUGIN_ROOT / "web_res" / "static" / "html" / "change_password.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "graph_share.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "index.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "login.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "macos.html",
]
EXTERNAL_ASSET_HOSTS = [
    "fonts.googleapis.com",
    "fonts.loli.net",
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "bootcdn.net",
    "unpkg.com",
    "lf26-cdn-tos.bytecdntp.com",
]


def test_webui_html_templates_no_external_frontend_cdn_refs():
    for path in HTML_FILES:
        text = path.read_text(encoding="utf-8")
        for host in EXTERNAL_ASSET_HOSTS:
            assert host not in text, f"{path.name} still references {host}"


def test_webui_frontend_vendor_assets_exist():
    expected_paths = [
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "echarts.min.js",
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "material-icons" / "material-icons.css",
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "material-icons" / "material-icons.woff2",
    ]

    for path in expected_paths:
        assert path.exists(), f"Missing vendored frontend asset: {path}"


def test_dashboard_exposes_learning_content_browser():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "学习内容" in text
    assert "/api/style_learning/content_text" in text
    assert "data-content-type=\"dialogues\"" in text
    assert "data-content-type=\"analysis\"" in text
    assert "data-content-type=\"features\"" in text
    assert "data-content-type=\"history\"" in text


def test_dashboard_exposes_structured_ai_insight_panel():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "AI 巡检" in text
    assert "buildDashboardInsights" in text
    assert "jumpToInsightTarget" in text
    assert "copyAiInsightContext" in text
    assert "aiInsightList" in text


def test_dashboard_exposes_tiered_dependency_install_controls():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "基础能力依赖" in text
    assert "全能力依赖" in text
    assert "installDependencyTier" in text
    assert "data-dependency-tier=\"basic\"" in text
    assert "data-dependency-tier=\"full\"" in text


def test_dashboard_filters_provider_selects_by_astrbot_provider_type():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "providerOptionsForField" in text
    assert "provider_options_by_type" in text
    assert "chat_completion: '聊天模型'" in text
    assert "embedding: 'Embedding'" in text
    assert "rerank: 'Reranker'" in text
    assert "未找到 ${escapeHtml(providerTypeLabel(field.provider_type))} Provider" in text


def test_dashboard_zero_message_insight_reflects_full_learning_default():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "默认全量学习等待消息" in text
    assert "目标列表留空时会学习所有非黑名单消息" in text
    assert "暂无消息进入学习链路" not in text
