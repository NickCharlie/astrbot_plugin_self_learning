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
PLUGIN_PAGE_FILES = [
    PLUGIN_ROOT / "pages" / "dashboard" / "index.html",
    PLUGIN_ROOT / "pages" / "dashboard" / "app.js",
    PLUGIN_ROOT / "pages" / "dashboard" / "styles.css",
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
    assert 'apiPost("settings/action"' in script
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
    assert "content-delete" in text
    assert "/api/style_learning/content_text/${encodeURIComponent(bucket)}/${encodeURIComponent(itemId)}" in text


def test_dashboard_review_details_use_backend_structured_fields():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "item && item.pattern_details" in text
    assert "item && item.few_shot_pairs" in text
    assert "renderStyleReviewDetails(item)" in text
    assert "renderChangePreview(item)" in text
    assert "persona_change_preview" in text
    assert "persona_change_snapshot" in text
    assert "before_system_prompt" in text
    assert "after_begin_dialogs" in text
    assert "/api/persona_updates/reviewed?limit=5" in text
    assert "reviewedPersonaList" in text
    assert "追加到 begin_dialogs" in text
    assert "item.definition || item.meaning || item.review_detail" in text
    assert "renderContextExamples(item)" in text


def test_dashboard_review_deletes_use_inline_confirmation():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "function showConfirm(title, message, confirmText)" in text
    assert "confirm-overlay" in text
    assert "showConfirm('删除审查记录', '确定删除这条审查记录？不可撤销。', '确认删除')" in text
    assert "showConfirm('删除黑话', '确定删除这条黑话？不可撤销。', '确认删除')" in text
    assert "window.confirm('确定删除这条审查记录" not in text
    assert "window.confirm('确定删除这条黑话" not in text


def test_dashboard_exposes_structured_ai_insight_panel():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "AI 巡检" in text
    assert "buildDashboardInsights" in text
    assert "jumpToInsightTarget" in text
    assert "copyAiInsightContext" in text
    assert "aiInsightList" in text


def test_dashboard_uses_module_home_and_hash_pages():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "模块入口" in text
    assert "data-page=\"home\"" in text
    assert "data-route-card=\"overview\"" in text
    assert "data-route-card=\"integrations\"" in text
    assert "data-route-card=\"settings\"" in text
    for page in ["overview", "insights", "monitoring", "reviews", "content", "reply-strategy", "graphs", "integrations", "settings"]:
        assert f"data-page=\"{page}\"" in text
        assert f"href=\"#/{page}\"" in text or page == "home"
    assert "resolvePageFromHash" in text
    assert "navigateToPage('settings')" in text


def test_dashboard_exposes_companion_plugin_api_hub():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")
    service = (PLUGIN_ROOT / "webui" / "services" / "integration_service.py").read_text(encoding="utf-8")

    assert "功能融合" in text
    assert "integrationCards" in text
    assert "integrationConfigFields" in text
    assert "Integration_Settings" in text
    assert "/api/integrations/status" in text + service
    assert "/api/integrations/embed/livingmemory" in text + service
    assert "/api/integrations/embed/group_chat_plus" in text + service
    assert "reply-strategy" in text + service
    assert "self_learning_graph_store_adapter" in service
    assert "astrbot_plugin_livingmemory/page" not in service
    assert "/api/plugin/page/content/astrbot_plugin_livingmemory/dashboard/" not in service
    assert "Group Chat Plus" in service
    assert "POST /api/auth/login" in service
    assert "GET /api/data/overview" in service


def test_dashboard_exposes_tiered_dependency_install_controls():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "基础能力依赖" in text
    assert "全能力依赖" in text
    assert "installDependencyTier" in text
    assert "data-dependency-tier=\"basic\"" in text
    assert "data-dependency-tier=\"full\"" in text
    assert "pipMirrorSelect" in text
    assert "pip_mirror" in text
    assert "清华大学 TUNA" in text


def test_dashboard_exposes_persona_review_diff_preview():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "renderChangePreview" in text
    assert "buildLineDiff" in text
    assert "before_system_prompt" in text
    assert "after_system_prompt" in text
    assert "before_begin_dialogs" in text
    assert "after_begin_dialogs" in text
    assert "追加到 begin_dialogs" in text
    assert "review-preview" in text


def test_dashboard_exposes_persona_state_and_backup_management():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "当前人格状态" in text
    assert "人格备份" in text
    assert "personaStateStats" in text
    assert "personaBackupList" in text
    assert "/api/persona_management/current?group_id=default" in text
    assert "/api/persona_backups/list?limit=8" in text
    assert "data-${key}" in text
    assert "group-id" in text
    assert "persona-backup-view" in text
    assert "persona-backup-restore" in text
    assert "persona-backup-delete" in text


def test_dashboard_filters_provider_selects_by_astrbot_provider_type():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "providerOptionsForField" in text
    assert "providerTypeLabelsFromSchema" in text
    assert "provider_options_by_type" in text
    assert "FALLBACK_PROVIDER_TYPE_LABELS" in text
    assert "chat_completion: '聊天模型'" in text
    assert "embedding: 'Embedding'" in text
    assert "rerank: 'Reranker'" in text
    assert "field.provider_type_label || providerTypeLabel(field.provider_type)" in text
    assert "const options = providerOptionsForField(field);" in text
    assert "else if (field.widget === 'provider' && providerOptionsForField(field).length)" not in text
    assert "未找到 ${escapeHtml(providerLabel)} Provider" in text


def test_dashboard_settings_exposes_manual_save_button():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert 'id="configSaveBtn"' in text
    assert 'aria-label="手动保存设置"' in text
    assert "手动保存设置" in text
    assert "configSaveBtn" in text
    assert "saveConfigPanel" in text
    assert "function updateConfigActionStates()" in text
    assert "configSaveBtn.disabled" in text
    assert "dirtyCount === 0" in text
    assert "!hasSchema || busy" in text
    assert "配置面板尚未加载" in text
    assert "正在保存配置" in text


def test_dashboard_zero_message_insight_reflects_full_learning_default():
    text = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")

    assert "默认全量学习等待消息" in text
    assert "目标列表留空时会学习所有非黑名单消息" in text
    assert "暂无消息进入学习链路" not in text


def test_force_graph_rendering_uses_stable_static_layout():
    dashboard = (PLUGIN_ROOT / "web_res" / "static" / "html" / "dashboard.html").read_text(encoding="utf-8")
    graph_share = (PLUGIN_ROOT / "web_res" / "static" / "html" / "graph_share.html").read_text(encoding="utf-8")

    for text in (dashboard, graph_share):
        assert "function computeStableGraphLayout" in text
        assert "function prepareGraphNodesForRender" in text
        assert "function graphHash" in text
        assert "positionCache" in text or "graphPositionCache" in text
        assert "layoutAnimation" not in text
        assert "repulsion:" not in text
        assert "gravity:" not in text
        assert "edgeLength:" not in text

    assert "layoutSettled" in dashboard
    assert "layout: isForceLayout ? 'none' : state.graph.layout" in dashboard
    assert "rememberDraggedGraphNode(chart, params)" in dashboard
    assert "graphLayoutSettled" in graph_share
    assert 'layout: isCircular ? "circular" : "none"' in graph_share
    assert "rememberDraggedNode(params)" in graph_share
