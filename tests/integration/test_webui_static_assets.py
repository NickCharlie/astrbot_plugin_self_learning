"""Regression tests for bundled WebUI frontend assets."""

import json
import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
# 仍在使用的服务端模板（登录、改密、图谱分享）。旧版单体 dashboard.html /
# index.html / macos.html 已由 web_src 构建的新版 Solid.js SPA 取代并移除。
HTML_FILES = [
    PLUGIN_ROOT / "web_res" / "static" / "html" / "change_password.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "graph_share.html",
    PLUGIN_ROOT / "web_res" / "static" / "html" / "login.html",
]
# 新版 SPA 产物（在 web_src 执行 `pnpm build` 输出到 web_res/static/dashboard）。
DASHBOARD_SPA_INDEX = PLUGIN_ROOT / "web_res" / "static" / "dashboard" / "index.html"
DASHBOARD_SPA_ASSETS = PLUGIN_ROOT / "web_res" / "static" / "dashboard" / "assets"
PLUGIN_PAGE_FILES = [
    PLUGIN_ROOT / "pages" / "dashboard" / "index.html",
    PLUGIN_ROOT / "pages" / "dashboard" / "app.js",
    PLUGIN_ROOT / "pages" / "dashboard" / "styles.css",
    PLUGIN_ROOT / "pages" / "dashboard" / "_page.json",
]
PLUGIN_I18N_FILES = [
    PLUGIN_ROOT / ".astrbot-plugin" / "i18n" / "zh-CN.json",
    PLUGIN_ROOT / ".astrbot-plugin" / "i18n" / "en-US.json",
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


def test_dashboard_spa_artifacts_exist():
    """新版 Solid.js SPA 产物必须随仓库部署，供 /api/ 入口直接 serve。"""
    assert DASHBOARD_SPA_INDEX.exists(), (
        "Missing dashboard SPA entry: web_res/static/dashboard/index.html"
    )
    assert DASHBOARD_SPA_ASSETS.is_dir(), "Missing dashboard SPA assets directory"
    text = DASHBOARD_SPA_INDEX.read_text(encoding="utf-8")
    # 产物应引用 /static/dashboard/assets 下的打包资源与 /static/vendor 图标。
    assert "/static/dashboard/assets/" in text
    assert "/static/vendor/material-icons/material-icons.css" in text
    for asset_name in re.findall(r'["\']/static/dashboard/assets/([^"\']+)["\']', text):
        assert (DASHBOARD_SPA_ASSETS / asset_name).exists(), (
            f"Dashboard SPA references missing asset: {asset_name}"
        )


def test_webui_html_templates_no_external_frontend_cdn_refs():
    for path in HTML_FILES:
        text = path.read_text(encoding="utf-8")
        for host in EXTERNAL_ASSET_HOSTS:
            assert host not in text, f"{path.name} still references {host}"


def test_embedded_plugin_page_assets_are_self_contained():
    for path in PLUGIN_PAGE_FILES:
        assert path.exists(), f"Missing embedded Plugin Page asset: {path}"
        text = path.read_text(encoding="utf-8")
        for host in EXTERNAL_ASSET_HOSTS:
            assert host not in text, f"{path.name} still references {host}"


def test_embedded_plugin_page_uses_astrbot_bridge_and_module_dashboard():
    index = (PLUGIN_ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")
    script = (PLUGIN_ROOT / "pages" / "dashboard" / "app.js").read_text(encoding="utf-8")
    styles = (PLUGIN_ROOT / "pages" / "dashboard" / "styles.css").read_text(encoding="utf-8")

    assert "AstrBot Embedded WebUI" in index
    for label in [
        "Dashboard",
        "AI 巡检",
        "监控",
        "审查队列",
        "黑话学习",
        "表达方式学习",
        "人格学习",
        "学习内容",
        "图谱",
        "回复策略",
        "功能融合",
        "设置",
    ]:
        assert label in index
    for page in [
        "home",
        "insights",
        "monitoring",
        "reviews",
        "jargon-learning",
        "expression-learning",
        "persona-learning",
        "content",
        "graphs",
        "reply-strategy",
        "integrations",
        "settings",
    ]:
        assert f'data-page="{page}"' in index
    assert "window.AstrBotPluginPage" in script
    assert 'apiGet("dashboard")' in script
    assert 'apiGet("jargon"' in script
    assert 'apiGet("style"' in script
    assert 'apiGet("persona"' in script
    assert 'apiGet("graphs"' in script
    assert 'apiPost("reviews/action"' in script
    assert 'apiPost("style/action"' in script
    assert 'apiPost("persona/action"' in script
    assert 'apiPost("settings/action"' in script
    assert 'data-batch-review-kind="persona"' in index
    assert 'data-batch-review-kind="style"' in index
    assert 'data-batch-review-kind="jargon"' in index
    assert "function handleBatchReviewAction" in script
    assert "batch_review_style" in script
    assert "batch_review_jargon" in script
    assert 'review_source !== "style_learning"' in script
    assert "分类去向" in script
    assert "style_learning_reviews" in script
    assert "persona_memory_reviews" in script
    assert 'data-jargon-action="edit"' in script
    assert 'data-style-action="edit"' in script
    assert 'data-persona-action="edit"' in script
    assert 'id="modal-jargon-save"' in script
    assert 'id="modal-style-save"' in script
    assert 'id="modal-persona-save"' in script
    assert "region.replaceChildren()" in script
    assert "toast-close" in script
    assert 'return `page/${String(path || "")' in script
    assert "initSpringMotion" in script
    assert "startGraphRender" in script
    assert "syncGraphCanvasSize" in script
    assert "hitGraphNode" in script
    assert "settleGraphLayout" in script
    assert "graphHomePosition" in script
    assert "GRAPH_HOME_STRENGTH" in script
    assert "graphNodeMargin" in script
    assert "manual_dependency_source" in script
    assert "installButton.disabled = true" in script
    assert "正在调用 pip 安装依赖" in script
    assert "function resolveHostUrl" in script
    assert "function localNavigationHost" in script
    assert "browserHost = window.location.hostname" in script
    assert 'resolveHostUrl(webui.dashboard_url || "")' in script
    assert "resolveHostUrl(link.url || \"#\")" in script
    assert "resolveHostUrl(dash.external_url || dash.official_page_url || dash.url || \"#\")" in script
    assert 'id="physics-canvas"' in index
    assert 'id="graph-canvas"' in index
    assert 'id="graph-canvas" width=' not in index
    assert 'id="full-dashboard-link" href="#"' in index
    assert "persona-layout" in index
    assert 'http://127.0.0.1:7833' not in index
    assert ".module-card" in styles
    assert ".ring-chart" in styles
    assert ".sidebar" in styles
    assert ".graph-panel" in styles
    assert ".persona-layout" in styles
    assert "overflow-wrap: anywhere" in styles
    assert "aspect-ratio: 16 / 9" in styles
    assert "button:disabled" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "touch-action: none" in styles


def test_embedded_plugin_page_i18n_resources_are_complete():
    for path in PLUGIN_I18N_FILES:
        assert path.exists(), f"Missing plugin i18n resource: {path}"

    zh = json.loads(PLUGIN_I18N_FILES[0].read_text(encoding="utf-8"))
    en = json.loads(PLUGIN_I18N_FILES[1].read_text(encoding="utf-8"))
    page_meta = json.loads((PLUGIN_ROOT / "pages" / "dashboard" / "_page.json").read_text(encoding="utf-8"))
    index = (PLUGIN_ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")
    script = (PLUGIN_ROOT / "pages" / "dashboard" / "app.js").read_text(encoding="utf-8")

    def leaf_keys(obj, prefix=""):
        if isinstance(obj, dict):
            keys = set()
            for key, value in obj.items():
                next_prefix = f"{prefix}.{key}" if prefix else key
                keys |= leaf_keys(value, next_prefix)
            return keys
        return {prefix}

    zh_keys = leaf_keys(zh)
    en_keys = leaf_keys(en)
    assert zh_keys == en_keys
    assert page_meta["title"]["i18n_key"] == "pages.dashboard.title"
    assert page_meta["description"]["i18n_key"] == "pages.dashboard.description"

    used_keys = set()
    for match in re.finditer(r'data-i18n(?:-[\w-]+)?="([^"]+)"', index):
        used_keys.add(f"pages.dashboard.{match.group(1)}")
    for match in re.finditer(r'(?<![A-Za-z0-9_$])t\("([^"]+)"', script):
        key = match.group(1)
        if not key.startswith(("pages.", "metadata.", "config.")):
            key = f"pages.dashboard.{key}"
        used_keys.add(key)

    missing_keys = sorted(key for key in used_keys if key not in zh_keys)
    assert not missing_keys


def test_webui_frontend_vendor_assets_exist():
    expected_paths = [
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "echarts.min.js",
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "material-icons" / "material-icons.css",
        PLUGIN_ROOT / "web_res" / "static" / "vendor" / "material-icons" / "material-icons.woff2",
    ]

    for path in expected_paths:
        assert path.exists(), f"Missing vendored frontend asset: {path}"


def test_embedded_plugin_page_uses_inline_confirmation_for_batch_actions():
    script = (PLUGIN_ROOT / "pages" / "dashboard" / "app.js").read_text(encoding="utf-8")

    assert "function showConfirm(title, message" in script
    assert "modal-confirm-ok" in script
    assert "modal.confirmBatch" in script
    assert "window.confirm(" not in script


def test_embedded_plugin_page_hides_review_buttons_for_confirmed_jargon():
    script = (PLUGIN_ROOT / "pages" / "dashboard" / "app.js").read_text(encoding="utf-8")

    assert 'item.is_confirmed ? "" : button(t("actions.confirm"' in script
    assert 'item.is_confirmed ? "" : button(t("actions.reject"' in script


def test_graph_share_rendering_uses_stable_static_layout():
    """graph_share.html 仍使用稳定的静态布局渲染（旧版单体 dashboard.html 已移除）。"""
    graph_share = (PLUGIN_ROOT / "web_res" / "static" / "html" / "graph_share.html").read_text(encoding="utf-8")

    assert "function computeStableGraphLayout" in graph_share
    assert "function prepareGraphNodesForRender" in graph_share
    assert "function graphHash" in graph_share
    assert "positionCache" in graph_share or "graphPositionCache" in graph_share
    assert "layoutAnimation" not in graph_share
    assert "repulsion:" not in graph_share
    assert "gravity:" not in graph_share
    assert "edgeLength:" not in graph_share

    assert "graphLayoutSettled" in graph_share
    assert 'layout: isCircular ? "circular" : "none"' in graph_share
    assert "rememberDraggedNode(params)" in graph_share
