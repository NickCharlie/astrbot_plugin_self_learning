(() => {
  "use strict";

  const PAGE_META = {
    home: ["Dashboard", "完整内嵌 WebUI"],
    insights: ["Insights", "AI 巡检"],
    monitoring: ["Monitoring", "运行监控"],
    reviews: ["Reviews", "审查队列"],
    "jargon-learning": ["Jargon", "黑话学习"],
    "expression-learning": ["Expression", "表达方式学习"],
    "persona-learning": ["Persona", "人格学习"],
    content: ["Content", "学习内容"],
    graphs: ["Graphs", "图谱"],
    "reply-strategy": ["Reply", "回复策略"],
    integrations: ["Integrations", "功能融合"],
    settings: ["Settings", "设置"],
  };
  const GRAPH_SAFE_PADDING = 34;
  const GRAPH_HOME_STRENGTH = 0.0064;
  const GRAPH_CENTER_STRENGTH = 0.00016;
  const GRAPH_LINK_STRENGTH = 0.000035;

  const state = {
    page: "home",
    ready: false,
    dashboard: null,
    overview: null,
    pageData: {},
    contentType: "dialogues",
    settingsGroup: null,
    dirtySettings: new Map(),
    graph: {
      nodes: [],
      links: [],
      running: false,
      dragged: null,
      hovered: null,
      type: "memory",
      width: 0,
      height: 0,
      canvasBound: false,
    },
    toastTimer: null,
  };

  const physics = {
    particles: [],
    pointer: { x: 0, y: 0, active: false },
    running: false,
    last: 0,
  };

  const $ = (id) => document.getElementById(id);
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function endpoint(path) {
    return `page/${String(path || "").replace(/^\/+/, "").replace(/\/+/g, "/")}`;
  }

  async function bridgeReady() {
    const bridge = window.AstrBotPluginPage;
    if (!bridge) {
      throw new Error("AstrBot 插件页桥接 SDK 未加载");
    }
    const context = await bridge.ready();
    state.ready = true;
    return context;
  }

  async function apiGet(path, params) {
    const bridge = window.AstrBotPluginPage;
    await bridgeReady();
    return unwrap(await bridge.apiGet(endpoint(path), params || {}));
  }

  async function apiPost(path, body) {
    const bridge = window.AstrBotPluginPage;
    await bridgeReady();
    return unwrap(await bridge.apiPost(endpoint(path), body || {}));
  }

  function unwrap(response) {
    const body = response && response.data && response.data.status ? response.data : response;
    if (body && body.status === "ok") {
      return body.data || {};
    }
    if (body && body.status === "error") {
      throw new Error(body.message || "请求失败");
    }
    if (body && body.success === false) {
      throw new Error(body.message || body.error || "请求失败");
    }
    return body || {};
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }

  function localNavigationHost(hostname) {
    const host = String(hostname || "").trim().replace(/^\[(.*)\]$/, "$1").toLowerCase();
    if (!host) return true;
    return host === "localhost"
      || host === "0.0.0.0"
      || host === "::"
      || host === "::1"
      || host === "0:0:0:0:0:0:0:0"
      || host === "0:0:0:0:0:0:0:1"
      || /^127(?:\.\d{1,3}){3}$/.test(host);
  }

  function hostForUrl(hostname) {
    const host = String(hostname || "").trim().replace(/^\[(.*)\]$/, "$1");
    return host.includes(":") ? `[${host}]` : host;
  }

  function resolveHostUrl(value) {
    const raw = String(value || "").trim();
    if (!raw || raw === "#") return raw || "#";
    if (raw.startsWith("#")) return raw;

    let parsed;
    try {
      parsed = new URL(raw, window.location.href);
    } catch (_) {
      return raw;
    }

    if (!/^https?:$/.test(parsed.protocol) || !localNavigationHost(parsed.hostname)) {
      return raw;
    }

    const browserHost = window.location.hostname;
    if (!browserHost) return raw;
    const replacementHost = hostForUrl(browserHost);
    parsed.host = parsed.port ? `${replacementHost}:${parsed.port}` : replacementHost;
    return parsed.href;
  }

  function fmt(value, digits = 1) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return "0";
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(num);
  }

  function normalizeScore(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return 0;
    return Math.max(0, Math.min(100, num <= 1 ? num * 100 : num));
  }

  function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
  }

  function setHtml(id, html) {
    const el = $(id);
    if (el) el.innerHTML = html;
  }

  function empty(text = "暂无数据") {
    return `<div class="empty-state">${escapeHtml(text)}</div>`;
  }

  function pill(text, tone = "") {
    return `<span class="mini-badge ${escapeAttr(tone)}">${escapeHtml(text)}</span>`;
  }

  function button(label, attrs = "", cls = "ghost-button") {
    return `<button class="${cls}" type="button" ${attrs}>${escapeHtml(label)}</button>`;
  }

  function setBusy(label = "加载中") {
    setText("runtime-status", label);
    setText("hero-status", label);
  }

  function showToast(message, tone = "ok") {
    const region = $("toast-region");
    if (!region) return;
    if (state.toastTimer) {
      clearTimeout(state.toastTimer);
      state.toastTimer = null;
    }
    region.replaceChildren();
    const el = document.createElement("div");
    el.className = `toast ${tone}`;
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.className = "toast-close";
    close.type = "button";
    close.setAttribute("aria-label", "关闭提示");
    close.textContent = "×";
    close.addEventListener("click", () => {
      if (state.toastTimer) clearTimeout(state.toastTimer);
      el.remove();
    });
    el.append(text, close);
    region.appendChild(el);
    state.toastTimer = setTimeout(() => {
      el.classList.add("leaving");
      setTimeout(() => {
        el.remove();
        if (state.toastTimer) state.toastTimer = null;
      }, 220);
    }, 3200);
  }

  function showErrors(errors) {
    const panel = $("error-panel");
    if (!panel) return;
    const entries = Object.entries(errors || {});
    panel.hidden = entries.length === 0;
    panel.innerHTML = entries
      .map(([key, value]) => `<p><strong>${escapeHtml(key)}</strong>: ${escapeHtml(value)}</p>`)
      .join("");
  }

  function showModal(title, html) {
    const modal = $("detail-modal");
    setText("modal-title", title);
    setHtml("modal-body", html);
    if (!modal) return;
    if (modal.open && typeof modal.close === "function") {
      modal.close();
    }
    if (typeof modal.showModal === "function") {
      try {
        modal.showModal();
        return;
      } catch (_) {}
    }
    modal.setAttribute("open", "");
  }

  function closeModal() {
    const modal = $("detail-modal");
    if (!modal) return;
    if (typeof modal.close === "function") modal.close();
    else modal.removeAttribute("open");
  }

  function resolvePageFromHash() {
    const raw = window.location.hash.replace(/^#\/?/, "");
    return PAGE_META[raw] ? raw : "home";
  }

  function navigateToPage(page, options = {}) {
    const next = PAGE_META[page] ? page : "home";
    state.page = next;
    if (!options.skipHash) {
      window.location.hash = `#/${next}`;
    }
    qsa(".page").forEach((el) => el.classList.toggle("active", el.dataset.page === next));
    qsa(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === next));
    const meta = PAGE_META[next] || PAGE_META.home;
    setText("page-kicker", meta[0]);
    setText("page-title", meta[1]);
    loadPageData(next, { force: !!options.force });
  }

  async function loadDashboard(force = false) {
    if (state.dashboard && !force) {
      renderDashboard(state.dashboard);
      return state.dashboard;
    }
    setBusy("同步中");
    try {
      const data = await apiGet("dashboard");
      state.dashboard = data;
      state.overview = data.overview || data;
      renderDashboard(data);
      return data;
    } catch (error) {
      showToast(error.message || String(error), "error");
      showErrors({ bridge: error.message || String(error) });
      throw error;
    }
  }

  async function loadPageData(page, options = {}) {
    const force = !!options.force;
    try {
      if (page === "home" || page === "insights") {
        const data = await loadDashboard(force);
        if (page === "insights") renderInsights(data);
        return;
      }
      if (page === "monitoring") return renderMonitoring(await cached("monitoring", () => apiGet("monitoring"), force));
      if (page === "reviews") return renderReviews(await cached("reviews", () => apiGet("reviews", { limit: 50 }), force));
      if (page === "jargon-learning") return loadJargon(force);
      if (page === "expression-learning") return renderStyle(await cached("style", () => apiGet("style", { limit: 50 }), force));
      if (page === "persona-learning") return renderPersona(await cached("persona", () => apiGet("persona", { group_id: "default", limit: 30 }), force));
      if (page === "content") return renderContent(await cached("content", () => apiGet("content", { page: 1, page_size: 20 }), force));
      if (page === "graphs") return loadGraphs(force);
      if (page === "reply-strategy") return renderReplyStrategy(await cached("integrations", () => apiGet("integrations"), force));
      if (page === "integrations") return renderIntegrations(await cached("integrations", () => apiGet("integrations"), force));
      if (page === "settings") return renderSettings(await cached("settings", () => apiGet("settings", { schema: "true" }), force));
    } catch (error) {
      showToast(error.message || String(error), "error");
    }
  }

  async function cached(key, loader, force) {
    if (!force && state.pageData[key]) return state.pageData[key];
    setBusy("加载中");
    const data = await loader();
    state.pageData[key] = data;
    return data;
  }

  function renderDashboard(data) {
    const overview = data.overview || data;
    const runtime = overview.runtime || {};
    const webui = overview.webui || {};
    const learning = overview.learning_stats || {};
    const jargon = overview.jargon || {};
    const styleStats = ((overview.style || {}).statistics) || {};
    const persona = overview.persona || {};
    const errors = data.errors || overview.errors || {};
    const degraded = runtime.database_degraded || Object.keys(errors).length > 0;

    const statusLabel = degraded ? "部分可用" : "运行正常";
    const resolvedDashboardUrl = resolveHostUrl(webui.dashboard_url || "");
    const summary = degraded
      ? "嵌入式页面已载入，部分服务处于降级状态。"
      : `已连接官方插件页 API，独立 WebUI: ${resolvedDashboardUrl || "未配置"}`;
    setText("runtime-status", statusLabel);
    setText("hero-status", statusLabel);
    setText("runtime-summary", summary);
    setText("hero-summary", summary);
    $("runtime-status")?.classList.toggle("warn", degraded);
    $("hero-status")?.classList.toggle("warn", degraded);

    const fullLink = $("full-dashboard-link");
    if (fullLink && resolvedDashboardUrl) fullLink.href = resolvedDashboardUrl;

    setText("stat-messages", fmt(learning.total_messages_collected));
    setText("stat-jargon", fmt(jargon.confirmed_jargon));
    setText("stat-style", fmt(styleStats.unique_styles || styleStats.total_samples));
    setText("stat-persona", fmt(learning.persona_updates || persona.begin_dialog_count));

    renderQuickActions(overview.quick_links || []);
    renderModuleCards(overview.modules || []);
    renderModuleChart(overview.modules || []);
    renderIntelligence(overview.metrics || {});
    renderInsights(data);
    showErrors(errors);
  }

  function renderQuickActions(links) {
    const html = links.map((link) => {
      const url = resolveHostUrl(link.url || "#");
      const external = /^https?:\/\//.test(String(url || ""));
      return `<a class="quick-entry" href="${escapeAttr(url || "#")}" target="${external ? "_blank" : "_self"}" rel="noreferrer">
        <span>${escapeHtml(link.label || "入口")}</span>
        <small>${escapeHtml(link.description || "")}</small>
      </a>`;
    }).join("");
    setHtml("quick-actions", html);
  }

  function renderModuleCards(modules) {
    const html = modules.map((item) => `
      <article class="module-card" style="--accent:${escapeAttr(item.accent || "#2563eb")}" data-route-card="${escapeAttr(item.target || "home")}">
        <div class="module-card-head">
          <h3>${escapeHtml(item.title)}</h3>
          ${pill(item.enabled ? "启用" : "关闭", item.enabled ? "ok" : "warn")}
        </div>
        <p>${escapeHtml(item.description || "")}</p>
        <div class="metric-line">
          <strong>${escapeHtml(fmt(item.metric))}</strong>
          <span>${escapeHtml(item.metric_label || "")}</span>
        </div>
      </article>
    `).join("");
    setHtml("module-card-grid", html || empty());
  }

  function renderModuleChart(modules) {
    const maxValue = Math.max(1, ...modules.map((item) => Number(item.metric || 0)));
    const html = modules.map((item) => {
      const value = Math.max(4, Math.min(100, (Number(item.metric || 0) / maxValue) * 100));
      return `<div class="bar-row" style="--accent:${escapeAttr(item.accent || "#2563eb")}">
        <span>${escapeHtml(item.title)}</span>
        <div class="bar-track"><div class="bar-fill" style="--value:${value}"></div></div>
        <strong>${escapeHtml(fmt(item.metric))}</strong>
      </div>`;
    }).join("");
    setHtml("module-chart", html || empty());
  }

  function renderIntelligence(metrics) {
    const score = normalizeScore(metrics.overall_score);
    $("intelligence-ring")?.style.setProperty("--value", String(score));
    setText("intelligence-score", fmt(score));
    const dimCount = metrics.dimensions && typeof metrics.dimensions === "object"
      ? Object.keys(metrics.dimensions).length
      : 0;
    setText("metrics-summary", dimCount ? `已有 ${dimCount} 个维度参与评估。` : "智能指标服务暂未产生维度数据。");
  }

  function buildInsights(data) {
    const overview = data.overview || {};
    const reviews = data.reviews || {};
    const monitoring = data.monitoring || {};
    const integrations = data.integrations || {};
    const errors = data.errors || {};
    const items = [];
    const push = (severity, title, detail, target) => items.push({ severity, title, detail, target });

    if ((overview.runtime || {}).database_degraded) {
      push("warn", "数据库处于降级状态", (overview.runtime || {}).database_error || "数据库服务未完整启动。", "monitoring");
    }
    const pendingPersona = ((reviews.persona_pending || {}).updates || []).length;
    const pendingStyle = ((reviews.style_reviews || {}).reviews || []).length;
    const pendingJargon = (((reviews.jargon_pending || {}).jargon_list) || []).length;
    const totalBacklog = pendingPersona + pendingStyle + pendingJargon;
    if (totalBacklog > 0) {
      push("action", "审查队列有积压", `当前有 ${totalBacklog} 条学习结果等待确认。`, "reviews");
    }
    const score = normalizeScore(((overview.metrics || {}).overall_score));
    if (score > 0 && score < 60) {
      push("warn", "智能评分偏低", `综合评分 ${fmt(score)}，建议查看表达样本和学习批次。`, "metrics");
    }
    const health = (monitoring.health || {}).overall;
    if (health && health !== "healthy") {
      push("warn", "健康检查提示异常", `当前健康状态为 ${health}。`, "monitoring");
    }
    const delegation = integrations.delegation || {};
    if (delegation.memory_delegated || delegation.reply_delegated) {
      push("ok", "伴随插件委托已启用", `记忆委托: ${delegation.memory_delegated ? "是" : "否"}，回复委托: ${delegation.reply_delegated ? "是" : "否"}。`, "integrations");
    }
    Object.entries(errors).forEach(([key, value]) => {
      push("warn", `模块 ${key} 读取失败`, String(value), "monitoring");
    });
    if (!items.length) {
      push("ok", "暂无高优先级问题", "核心学习、审查和监控模块均已返回可用数据。", "home");
    }
    return items;
  }

  function renderInsights(data) {
    const insights = buildInsights(data || state.dashboard || {});
    const html = insights.map((item) => `
      <article class="insight-card ${escapeAttr(item.severity)}">
        <span>${escapeHtml(item.severity === "ok" ? "OK" : item.severity === "action" ? "ACTION" : "WARN")}</span>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.detail)}</p>
        ${button("前往", `data-route-card="${escapeAttr(item.target)}"`)}
      </article>
    `).join("");
    setHtml("ai-insight-list", html);
  }

  function renderMonitoring(data) {
    const health = data.health || {};
    const checks = health.checks || {};
    const healthHtml = Object.entries(checks).map(([key, item]) => `
      <article class="health-card ${escapeAttr(item.status || "")}">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(item.status || "unknown")}</strong>
        <small>${escapeHtml(summarizeObject(item.detail || {}))}</small>
      </article>
    `).join("");
    setHtml("health-grid", healthHtml || empty("暂无健康检查数据"));

    const functions = ((data.functions || {}).functions || []).slice(0, 20);
    const fnHtml = functions.map((item) => `
      <div class="table-row">
        <span>${escapeHtml(shortName(item.name))}</span>
        <strong>${escapeHtml(fmt((item.duration || {}).avg || 0, 4))}s</strong>
        <small>${escapeHtml(fmt(item.calls || 0, 0))} calls</small>
      </div>
    `).join("");
    setHtml("function-list", fnHtml || empty((data.functions || {}).debug_mode ? "暂无函数性能数据" : "debug_mode 未启用"));
    showErrors(data.errors || {});
  }

  async function loadJargon(force) {
    const confirmed = $("jargon-confirmed")?.value || "";
    const filter = $("jargon-filter")?.value || "";
    const keyword = $("jargon-keyword")?.value || "";
    const params = { page: 1, page_size: 30 };
    if (confirmed) params.confirmed = confirmed;
    if (filter) params.filter = filter;
    if (keyword) params.keyword = keyword;
    const data = await cached(`jargon:${JSON.stringify(params)}`, () => apiGet("jargon", params), force);
    renderJargon(data);
  }

  function renderJargon(data) {
    const stats = data.stats || {};
    setHtml("jargon-stat-grid", statCards([
      ["候选词", stats.total_candidates],
      ["已确认", stats.confirmed_jargon],
      ["推断完成", stats.completed_inference],
      ["活跃群组", stats.active_groups],
    ]));
    const items = ((data.list || {}).jargon_list || []);
    const html = items.map((item) => `
      <div class="table-row rich-row">
        <div>
          <strong>${escapeHtml(item.term || item.content || `#${item.id}`)}</strong>
          <small>${escapeHtml(item.meaning || item.definition || "暂无释义")}</small>
        </div>
        <span>${escapeHtml(item.group_id || "global")}</span>
        ${pill(item.is_confirmed ? "已确认" : "待确认", item.is_confirmed ? "ok" : "warn")}
        ${pill(item.is_global ? "全局" : "本地")}
        <div class="row-actions">
          ${button("编辑", `data-jargon-action="edit" data-id="${escapeAttr(item.id)}"`)}
          ${button("确认", `data-jargon-action="approve" data-id="${escapeAttr(item.id)}"`)}
          ${button("驳回", `data-jargon-action="reject" data-id="${escapeAttr(item.id)}"`)}
          ${button(item.is_global ? "取消全局" : "设为全局", `data-jargon-action="toggle_global" data-id="${escapeAttr(item.id)}"`)}
          ${button("删除", `data-jargon-action="delete" data-id="${escapeAttr(item.id)}"`, "danger-button")}
        </div>
      </div>
    `).join("");
    setHtml("jargon-list", html || empty("暂无黑话数据"));
    state.pageData.lastJargonItems = items;
    showErrors(data.errors || {});
  }

  function renderStyle(data) {
    const stats = ((data.results || {}).statistics) || {};
    setHtml("style-stat-grid", statCards([
      ["风格样本", stats.unique_styles || stats.total_samples],
      ["平均置信度", stats.avg_confidence],
      ["总样本", stats.total_samples],
      ["最近更新", stats.latest_update ? "有" : "无"],
    ]));
    const patterns = data.patterns || {};
    const patternGroups = [
      ["情绪模式", patterns.emotion_patterns || []],
      ["语言模式", patterns.language_patterns || []],
      ["话题模式", patterns.topic_patterns || []],
    ];
    setHtml("style-pattern-columns", patternGroups.map(([title, list]) => `
      <div class="pattern-column">
        <h4>${escapeHtml(title)}</h4>
        ${(list || []).slice(0, 12).map((item) => `<span>${escapeHtml(item.name || item.pattern || item.text || "")}</span>`).join("") || empty("暂无模式")}
      </div>
    `).join(""));
    const chartItems = patternGroups.map(([title, list]) => ({ title, metric: (list || []).length, accent: "#4169e1" }));
    renderGenericBarChart("style-pattern-chart", chartItems);
    const reviews = ((data.reviews || {}).reviews || []);
    setHtml("expression-review-list", reviews.map((item) => styleReviewHtml(item)).join("") || empty("暂无表达审查"));
    state.pageData.lastStyleItems = reviews;
  }

  function renderReviews(data) {
    const personaPending = ((data.persona_pending || {}).updates || [])
      .filter((item) => item && item.review_source !== "style_learning");
    const personaReviewed = ((data.persona_reviewed || {}).updates || []);
    const styleReviews = ((data.style_reviews || {}).reviews || []);
    const pendingJargon = (((data.jargon_pending || {}).jargon_list) || []);
    setText("persona-review-count", fmt(personaPending.length, 0));
    setText("style-review-count", fmt(styleReviews.length, 0));
    setText("jargon-review-count", fmt(pendingJargon.length, 0));
    setText("reviewed-count", fmt(personaReviewed.length, 0));
    setHtml("persona-review-list", personaPending.map((item) => personaReviewHtml(item)).join("") || empty("暂无人格更新"));
    setHtml("style-review-list", styleReviews.map((item) => styleReviewHtml(item)).join("") || empty("暂无表达审查"));
    setHtml("jargon-review-list", pendingJargon.map((item) => jargonReviewHtml(item)).join("") || empty("暂无黑话候选"));
    state.pageData.lastStyleItems = styleReviews;
    setHtml("reviewed-persona-list", personaReviewed.slice(0, 12).map((item) => `
      <div class="table-row">
        <span>${escapeHtml(item.id)}</span>
        <strong>${escapeHtml(item.status || item.review_status || "reviewed")}</strong>
        <small>${escapeHtml(item.reason || item.update_type || item.review_source || "")}</small>
      </div>
    `).join("") || empty("暂无已审查记录"));
    showErrors(data.errors || {});
  }

  function personaReviewHtml(item) {
    const id = item.id;
    return `<article class="review-item">
      <div class="review-main">
        <strong>${escapeHtml(item.update_type || item.review_source || "人格更新")}</strong>
        <small>${escapeHtml(item.group_id || "default")} · ${escapeHtml(item.reason || item.description || "")}</small>
        <p>${escapeHtml(item.proposed_content || item.new_content || item.incremental_content || "").slice(0, 220)}</p>
      </div>
      <div class="row-actions">
        ${button("详情", `data-review-action="detail" data-kind="persona" data-id="${escapeAttr(id)}"`)}
        ${button("批准", `data-review-action="approve" data-kind="persona" data-id="${escapeAttr(id)}"`, "solid-button")}
        ${button("拒绝", `data-review-action="reject" data-kind="persona" data-id="${escapeAttr(id)}"`)}
        ${button("删除", `data-review-action="delete" data-kind="persona" data-id="${escapeAttr(id)}"`, "danger-button")}
      </div>
    </article>`;
  }

  function styleReviewHtml(item) {
    return `<article class="review-item">
      <div class="review-main">
        <strong>${escapeHtml(item.description || "表达方式学习")}</strong>
        <small>${escapeHtml(item.group_id || "default")} · ${escapeHtml(item.status || "pending")}</small>
        <p>${escapeHtml(item.few_shots_content || item.learned_patterns || "").slice(0, 220)}</p>
      </div>
      <div class="row-actions">
        ${button("编辑", `data-style-action="edit" data-id="${escapeAttr(item.id)}"`)}
        ${button("详情", `data-review-action="detail" data-kind="style" data-id="${escapeAttr(item.id)}"`)}
        ${button("批准", `data-review-action="approve" data-kind="style" data-id="${escapeAttr(item.id)}"`, "solid-button")}
        ${button("拒绝", `data-review-action="reject" data-kind="style" data-id="${escapeAttr(item.id)}"`)}
      </div>
    </article>`;
  }

  function jargonReviewHtml(item) {
    return `<article class="review-item">
      <div class="review-main">
        <strong>${escapeHtml(item.term || item.content || `#${item.id}`)}</strong>
        <small>${escapeHtml(item.group_id || "global")} · ${escapeHtml(fmt(item.occurrences || item.count, 0))} 次</small>
        <p>${escapeHtml(item.meaning || item.definition || item.review_detail || "暂无释义")}</p>
      </div>
      <div class="row-actions">
        ${button("确认", `data-review-action="approve" data-kind="jargon" data-id="${escapeAttr(item.id)}"`, "solid-button")}
        ${button("驳回", `data-review-action="reject" data-kind="jargon" data-id="${escapeAttr(item.id)}"`)}
        ${button("删除", `data-review-action="delete" data-kind="jargon" data-id="${escapeAttr(item.id)}"`, "danger-button")}
      </div>
    </article>`;
  }

  function renderPersona(data) {
    const current = data.current || {};
    const persona = current.persona || {};
    setHtml("persona-state-stats", statCards([
      ["提示词字数", current.prompt_length],
      ["开场对话", current.begin_dialog_count],
      ["工具数量", current.tool_count],
      ["当前群组", current.group_id || "default"],
    ]));
    setText("persona-prompt-preview", current.prompt_preview || persona.system_prompt || persona.prompt || "暂无人格提示词");

    const personas = data.personas || [];
    setHtml("persona-list", personas.map((item) => {
      const id = item.persona_id || item.id || item.name;
      return `<div class="table-row">
        <span>${escapeHtml(id)}</span>
        <strong>${escapeHtml(item.name || id)}</strong>
        <div class="row-actions">
          ${button("编辑", `data-persona-action="edit" data-persona-id="${escapeAttr(id)}"`)}
          ${button("导出", `data-persona-action="export" data-persona-id="${escapeAttr(id)}"`)}
          ${button("删除", `data-persona-action="delete" data-persona-id="${escapeAttr(id)}"`, "danger-button")}
        </div>
      </div>`;
    }).join("") || empty("暂无人格列表"));
    state.pageData.lastPersonaItems = personas;

    const backups = ((data.backups || {}).backups || []);
    setText("persona-backup-count", fmt(backups.length, 0));
    setHtml("persona-backup-list", backups.map((item) => `
      <div class="table-row rich-row">
        <div>
          <strong>${escapeHtml(item.backup_name || `备份 ${item.id}`)}</strong>
          <small>${escapeHtml(item.reason_short || item.reason || "无备注")}</small>
        </div>
        <span>${escapeHtml(item.group_id || "default")}</span>
        <small>${escapeHtml(item.timestamp || item.created_at || "")}</small>
        <div class="row-actions">
          ${button("查看", `data-persona-action="backup_detail" data-id="${escapeAttr(item.id)}" data-group-id="${escapeAttr(item.group_id || "")}"`)}
          ${button("恢复", `data-persona-action="backup_restore" data-id="${escapeAttr(item.id)}" data-group-id="${escapeAttr(item.group_id || "")}"`, "solid-button")}
          ${button("删除", `data-persona-action="backup_delete" data-id="${escapeAttr(item.id)}" data-group-id="${escapeAttr(item.group_id || "")}"`, "danger-button")}
        </div>
      </div>
    `).join("") || empty("暂无人格备份"));
    showErrors(data.errors || {});
  }

  function renderContent(data) {
    const content = data.content || {};
    const items = content[state.contentType] || [];
    qsa("#content-tabs button").forEach((btn) => btn.classList.toggle("active", btn.dataset.contentType === state.contentType));
    setHtml("learning-content-list", items.map((item) => `
      <article class="content-item">
        <div>
          <strong>${escapeHtml(item.title || item.type || `#${item.id}`)}</strong>
          <small>${escapeHtml(item.timestamp || "")} ${escapeHtml(item.metadata || "")}</small>
          <p>${escapeHtml(item.text || item.detail || "").slice(0, 360)}</p>
        </div>
        ${button("删除", `data-content-action="delete_content" data-bucket="${escapeAttr(state.contentType)}" data-id="${escapeAttr(item.id)}"`, "danger-button")}
      </article>
    `).join("") || empty("暂无学习内容"));

    const batches = ((data.batches || {}).batches || []);
    setHtml("batch-list", batches.map((item) => `
      <div class="table-row">
        <span>${escapeHtml(item.batch_name || item.batch_id || item.id)}</span>
        <strong>${escapeHtml(item.status || (item.success ? "success" : "unknown"))}</strong>
        <small>${escapeHtml(fmt(item.quality_score || 0, 3))}</small>
        ${button("删除", `data-content-action="delete_batch" data-id="${escapeAttr(item.id)}"`, "danger-button")}
      </div>
    `).join("") || empty("暂无批次历史"));
    showErrors(data.errors || {});
  }

  async function loadGraphs(force) {
    const type = $("graph-type")?.value || "memory";
    state.graph.type = type;
    const data = await cached(`graphs:${type}`, () => apiGet("graphs", { type, limit: 140 }), force);
    renderGraphs(data);
  }

  function renderGraphs(data) {
    const graph = data[state.graph.type] || data.memory || data.knowledge || {};
    const canvas = $("graph-canvas");
    const size = canvas
      ? syncGraphCanvasSize(canvas, { force: true })
      : { width: 960, height: 520 };
    const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
    state.graph.nodes = rawNodes.map((node, index) =>
      createGraphNode(node, index, rawNodes.length, size.width, size.height),
    );
    state.graph.links = normalizeGraphLinks(graph.links || []);
    settleGraphLayout(state.graph.nodes, state.graph.links, size.width, size.height);
    state.graph.dragged = null;
    state.graph.hovered = null;
    setHtml("graph-stat-grid", statCards([
      ["节点", (graph.stats || {}).nodes || state.graph.nodes.length],
      ["连线", (graph.stats || {}).links || state.graph.links.length],
      ["群组", (graph.stats || {}).groups || (graph.groups || []).length],
      ["来源", graph.data_source || "self_learning"],
    ]));
    setHtml("graph-node-list", state.graph.nodes.slice(0, 18).map((node) => `
      <div class="table-row">
        <span>${escapeHtml(node.name || node.id)}</span>
        <strong>${escapeHtml(node.category_name || node.category || "节点")}</strong>
        <small>${escapeHtml(node.detail || "")}</small>
      </div>
    `).join("") || empty("暂无图谱节点"));
    startGraphRender();
  }

  function createGraphNode(node, index, total, width, height) {
    const id = graphValueKey(node.id ?? node.name ?? node.label ?? `${state.graph.type}-${index}`);
    const radius = graphNodeRadius(node);
    const safeWidth = Math.max(320, width || 960);
    const safeHeight = Math.max(320, height || 520);
    const home = graphHomePosition(id, index, total, safeWidth, safeHeight, radius);
    return {
      ...node,
      id,
      label: node.name || node.label || id,
      radius,
      x: home.x,
      y: home.y,
      homeX: home.x,
      homeY: home.y,
      vx: 0,
      vy: 0,
      pinned: false,
    };
  }

  function graphHomePosition(id, index, total, width, height, radius) {
    const margin = graphNodeMargin(radius);
    const centerX = width / 2;
    const centerY = height / 2;
    const seed = graphStableSeed(id);
    const angleOffset = state.graph.type === "knowledge" ? 0.72 : 0;
    const angle = index * 2.399963229728653 + angleOffset + seed * 0.0007;
    const ring = Math.sqrt((index + 0.5) / Math.max(1, total));
    const spreadX = Math.max(86, (width - margin * 2) * 0.36);
    const spreadY = Math.max(72, (height - margin * 2) * 0.34);
    return {
      x: clamp(centerX + Math.cos(angle) * spreadX * ring, margin, width - margin),
      y: clamp(centerY + Math.sin(angle) * spreadY * ring, margin, height - margin),
    };
  }

  function settleGraphLayout(nodes, links, width, height) {
    if (!nodes.length) return;
    const byId = new Map(nodes.map((node) => [String(node.id), node]));
    for (let iteration = 0; iteration < 18; iteration += 1) {
      links.slice(0, 220).forEach((link) => {
        const source = byId.get(String(link.source));
        const target = byId.get(String(link.target));
        if (!source || !target) return;
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const desired = Math.max(78, Math.min(132, Math.min(width, height) * 0.23));
        const adjust = (dist - desired) * 0.0035;
        const nx = dx / dist;
        const ny = dy / dist;
        if (!source.pinned) {
          source.x += nx * adjust;
          source.y += ny * adjust;
        }
        if (!target.pinned) {
          target.x -= nx * adjust;
          target.y -= ny * adjust;
        }
      });

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < Math.min(nodes.length, i + 42); j += 1) {
          separateGraphNodes(nodes[i], nodes[j], 0.45);
        }
      }

      nodes.forEach((node) => {
        if (!node.pinned) {
          node.x += (node.homeX - node.x) * 0.12;
          node.y += (node.homeY - node.y) * 0.12;
        }
        clampGraphNode(node, width, height);
      });
    }
  }

  function normalizeGraphLinks(links) {
    if (!Array.isArray(links)) return [];
    return links.map((link) => ({
      ...link,
      source: graphValueKey(link.source ?? link.from),
      target: graphValueKey(link.target ?? link.to),
    })).filter((link) => link.source && link.target);
  }

  function renderReplyStrategy(data) {
    const cards = (data.dashboards || []).filter((item) => item.id === "group_chat_plus");
    setHtml("reply-strategy-cards", cards.map(integrationCardHtml).join("") || empty("未检测到 Group Chat Plus"));
  }

  function renderIntegrations(data) {
    setHtml("integration-cards", (data.dashboards || []).map(integrationCardHtml).join("") || empty("暂无融合状态"));
    const settings = data.settings || {};
    setHtml("integration-settings", Object.entries(settings).map(([key, value]) => `
      <div class="table-row">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(value === true ? "开启" : value === false ? "关闭" : value ?? "未设置")}</strong>
      </div>
    `).join("") || empty("暂无融合设置"));
    renderMaiBotImportPreview(data.maibot_learning || null);
  }

  function integrationCardHtml(item) {
    const dash = item.dashboard || {};
    const url = resolveHostUrl(dash.external_url || dash.official_page_url || dash.url || "#");
    const disabled = !dash.available || !url || url === "#";
    return `<article class="integration-card ${item.active ? "active" : ""}">
      <div>
        <span>${escapeHtml(item.role || "")}</span>
        <h3>${escapeHtml(item.title || item.id)}</h3>
        <p>${escapeHtml(item.delegated ? "已委托" : item.active ? "可用" : "未启用")}</p>
      </div>
      <a class="ghost-button ${disabled ? "disabled" : ""}" href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${escapeHtml(dash.label || "打开")}</a>
      <small>${escapeHtml((item.dev_api || {}).mode || "")}</small>
    </article>`;
  }

  function collectMaiBotPayload() {
    const payload = {
      maibot_root: $("maibot-root-input")?.value?.trim() || "",
      db_path: $("maibot-db-input")?.value?.trim() || "",
      memorix_db_path: $("maibot-memorix-input")?.value?.trim() || "",
      default_group_id: $("maibot-default-group-input")?.value?.trim() || "global",
      import_expressions: Boolean($("maibot-import-expressions")?.checked),
      import_jargons: Boolean($("maibot-import-jargons")?.checked),
      import_memories: Boolean($("maibot-import-memories")?.checked),
      approve_checked_expressions: Boolean($("maibot-approve-checked")?.checked),
    };
    if (!payload.maibot_root && !payload.db_path) {
      throw new Error("请填写 MaiBot 项目目录或主数据库路径");
    }
    return payload;
  }

  function renderMaiBotImportPreview(summary) {
    const output = $("maibot-import-output");
    if (!output || !summary) return;
    const counts = summary.counts || {};
    const breakdown = summary.review_breakdown || {};
    const destinations = summary.destinations || {};
    const lines = [];
    if (Object.keys(counts).length) {
      lines.push(`预览: 表达 ${fmt(counts.expressions, 0)} · 黑话 ${fmt(counts.jargons, 0)} · 记忆 ${fmt(counts.memories, 0)}`);
    }
    if (Object.keys(breakdown).length) {
      lines.push(`导入: 表达审查 ${fmt(breakdown.style_learning_reviews, 0)} · 黑话候选 ${fmt(breakdown.jargon_candidates, 0)} · 记忆审查 ${fmt(breakdown.persona_memory_reviews, 0)}`);
    }
    if (Object.keys(destinations).length) {
      lines.push(`分类去向: 表达 -> ${destinations.expressions}; 黑话 -> ${destinations.jargons}; 记忆 -> ${destinations.memories}`);
    }
    output.textContent = `${lines.join("\n")}${lines.length ? "\n\n" : ""}${JSON.stringify(summary, null, 2)}`;
  }

  function currentBatchReviewIds(kind) {
    const reviews = state.pageData.reviews || {};
    if (kind === "persona") {
      return ((reviews.persona_pending || {}).updates || [])
        .filter((item) => item && item.review_source !== "style_learning")
        .map((item) => item.id)
        .filter((id) => id !== undefined && id !== null && String(id) !== "");
    }
    if (kind === "style") {
      return ((reviews.style_reviews || {}).reviews || [])
        .map((item) => item.id)
        .filter((id) => id !== undefined && id !== null && String(id) !== "");
    }
    if (kind === "jargon") {
      return (((reviews.jargon_pending || {}).jargon_list) || [])
        .map((item) => item.id)
        .filter((id) => id !== undefined && id !== null && String(id) !== "");
    }
    return [];
  }

  async function handleBatchReviewAction(kind, action) {
    const ids = currentBatchReviewIds(kind);
    if (!ids.length) {
      showToast("当前页没有可批量处理的审查项", "error");
      return;
    }
    const typeText = { persona: "人格更新", style: "表达审查", jargon: "黑话候选" }[kind] || "审查项";
    const actionText = action === "approve" ? "通过" : "拒绝";
    if (!window.confirm(`确定批量${actionText}当前页 ${ids.length} 条${typeText}？`)) return;

    const payload = {
      action: kind === "persona" ? "batch_review" : kind === "style" ? "batch_review_style" : "batch_review_jargon",
      ids,
      decision: action,
    };
    const result = await apiPost("reviews/action", payload);
    showToast(result.message || "批量审查完成", result.success ? "ok" : "error");
    state.pageData.reviews = null;
    await loadPageData(state.page, { force: true });
  }

  async function runMaiBotImportAction(action) {
    const buttonEl = action === "maibot_import" ? $("maibot-import-button") : $("maibot-preview-button");
    const originalLabel = buttonEl?.textContent || "";
    try {
      const payload = collectMaiBotPayload();
      if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.classList.add("is-busy");
        buttonEl.textContent = action === "maibot_import" ? "导入中" : "预览中";
      }
      setText("maibot-import-output", "正在读取 MaiBot 学习数据...");
      const result = await apiPost("integrations/action", { action, ...payload });
      const detail = result.preview || result.result || result.payload || result;
      renderMaiBotImportPreview(detail);
      showToast(result.message || "MaiBot 学习数据操作完成", result.success !== false ? "ok" : "error");
      if (action === "maibot_import") {
        state.pageData = {};
        await loadDashboard(true);
      }
    } catch (error) {
      const message = error.message || String(error);
      setText("maibot-import-output", message);
      showToast(message, "error");
    } finally {
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.classList.remove("is-busy");
        buttonEl.textContent = originalLabel;
      }
    }
  }

  function renderSettings(data) {
    const schema = data.schema || {};
    const groups = schema.groups || [];
    if (!state.settingsGroup && groups.length) state.settingsGroup = groups[0].key;
    setHtml("settings-groups", groups.map((group) => `
      <button class="settings-group ${group.key === state.settingsGroup ? "active" : ""}" type="button" data-settings-group="${escapeAttr(group.key)}">
        <strong>${escapeHtml(group.title || group.key)}</strong>
        <small>${escapeHtml(group.hint || "")}</small>
      </button>
    `).join("") || empty("配置 schema 暂不可用"));

    const active = groups.find((group) => group.key === state.settingsGroup) || groups[0] || { fields: [] };
    setHtml("config-form", (active.fields || []).map(fieldHtml).join("") || empty("请选择配置分组"));
    renderPipMirrors(data.pip_mirrors || {});
  }

  function fieldHtml(field) {
    const value = state.dirtySettings.has(field.key) ? state.dirtySettings.get(field.key) : field.value;
    const common = `data-config-field="${escapeAttr(field.key)}" data-config-type="${escapeAttr(field.type)}" ${field.editable ? "" : "disabled"}`;
    let control = "";
    if (field.widget === "toggle") {
      control = `<label class="switch"><input type="checkbox" ${common} ${value ? "checked" : ""}><span></span></label>`;
    } else if (field.widget === "select" || field.widget === "provider") {
      const options = field.options || [];
      control = `<select ${common}>${options.map((option) => `<option value="${escapeAttr(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label || option.value)}</option>`).join("")}</select>`;
    } else if (field.widget === "textarea" || field.type === "list") {
      const textValue = Array.isArray(value) ? value.join("\n") : value ?? "";
      control = `<textarea rows="4" ${common}>${escapeHtml(textValue)}</textarea>`;
    } else {
      const inputType = field.widget === "number" || field.type === "int" || field.type === "float" ? "number" : "text";
      const step = field.type === "float" ? "0.01" : "1";
      control = `<input type="${inputType}" step="${step}" value="${escapeAttr(value ?? "")}" ${common}>`;
    }
    return `<label class="config-field">
      <span>
        <strong>${escapeHtml(field.label || field.key)}</strong>
        <small>${escapeHtml(field.hint || "")}${field.restart_required ? " · 重启后生效" : ""}</small>
      </span>
      ${control}
    </label>`;
  }

  function renderPipMirrors(mirrors) {
    const select = $("pip-mirror-select");
    if (!select || select.childElementCount) return;
    select.innerHTML = Object.entries(mirrors).map(([key, item]) => `<option value="${escapeAttr(key)}">${escapeHtml(item.label || key)}</option>`).join("");
  }

  function statCards(items) {
    return items.map(([label, value]) => `<article class="stat-card small">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(fmt(value, typeof value === "number" ? 1 : 0))}</strong>
    </article>`).join("");
  }

  function renderGenericBarChart(id, items) {
    const maxValue = Math.max(1, ...items.map((item) => Number(item.metric || 0)));
    setHtml(id, items.map((item) => {
      const value = Math.max(4, Math.min(100, Number(item.metric || 0) / maxValue * 100));
      return `<div class="bar-row" style="--accent:${escapeAttr(item.accent || "#4169e1")}">
        <span>${escapeHtml(item.title)}</span>
        <div class="bar-track"><div class="bar-fill" style="--value:${value}"></div></div>
        <strong>${escapeHtml(fmt(item.metric, 0))}</strong>
      </div>`;
    }).join("") || empty());
  }

  function summarizeObject(obj) {
    const entries = Object.entries(obj || {}).slice(0, 3);
    return entries.map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · ");
  }

  function shortName(name) {
    const text = String(name || "");
    return text.length > 58 ? `...${text.slice(-55)}` : text;
  }

  function findReviewItem(kind, id) {
    const reviews = state.pageData.reviews || {};
    const style = state.pageData.style || {};
    if (kind === "persona") return ((reviews.persona_pending || {}).updates || []).find((item) => String(item.id) === String(id));
    if (kind === "style") {
      return (
        ((reviews.style_reviews || {}).reviews || []).find((item) => String(item.id) === String(id))
        || ((style.reviews || {}).reviews || []).find((item) => String(item.id) === String(id))
      );
    }
    return (((reviews.jargon_pending || {}).jargon_list || []).find((item) => String(item.id) === String(id)));
  }

  async function handleReviewAction(kind, id, action) {
    if (action === "detail") {
      showModal("审查详情", `<pre class="code-preview">${escapeHtml(JSON.stringify(findReviewItem(kind, id) || {}, null, 2))}</pre>`);
      return;
    }
    let payload;
    if (kind === "persona") {
      payload = action === "delete"
        ? { action: "delete", id }
        : { action: "review", id, decision: action };
    } else if (kind === "style") {
      payload = { action: `style_${action}`, id };
    } else {
      payload = { action: `jargon_${action}`, id };
    }
    const result = await apiPost("reviews/action", payload);
    showToast(result.message || "操作完成", result.success ? "ok" : "error");
    state.pageData.reviews = null;
    await loadPageData(state.page, { force: true });
  }

  async function handleJargonAction(action, id) {
    if (action === "edit") {
      const item = (state.pageData.lastJargonItems || []).find((entry) => String(entry.id) === String(id)) || {};
      showModal("编辑黑话", `
        <label class="config-field"><span><strong>词条</strong></span><input id="modal-jargon-content" value="${escapeAttr(item.term || item.content || "")}"></label>
        <label class="config-field"><span><strong>释义</strong></span><textarea id="modal-jargon-meaning" rows="4">${escapeHtml(item.meaning || item.definition || "")}</textarea></label>
        <button class="solid-button" type="button" id="modal-jargon-save" data-id="${escapeAttr(id)}">保存</button>
      `);
      return;
    }
    const result = await apiPost("jargon/action", { action, id });
    showToast(result.message || "操作完成", result.success ? "ok" : "error");
    state.pageData = {};
    await loadPageData(state.page, { force: true });
  }

  function modalFieldValue(id) {
    return $(id)?.value ?? "";
  }

  function parseModalJson(id, fallback) {
    const raw = modalFieldValue(id).trim();
    if (!raw) return fallback;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return raw.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    }
  }

  async function handleStyleAction(action, id) {
    if (action === "edit") {
      const item = (state.pageData.lastStyleItems || []).find((entry) => String(entry.id) === String(id)) || {};
      const patterns = typeof item.learned_patterns === "string"
        ? item.learned_patterns
        : JSON.stringify(item.learned_patterns || [], null, 2);
      showModal("编辑表达方式", `
        <label class="config-field"><span><strong>描述</strong></span><input id="modal-style-description" value="${escapeAttr(item.description || "")}"></label>
        <label class="config-field"><span><strong>Few-shot 示例</strong></span><textarea id="modal-style-few-shots" rows="7">${escapeHtml(item.few_shots_content || "")}</textarea></label>
        <label class="config-field"><span><strong>学习模式 JSON</strong></span><textarea id="modal-style-patterns" rows="7">${escapeHtml(patterns)}</textarea></label>
        <button class="solid-button" type="button" id="modal-style-save" data-id="${escapeAttr(id)}">保存</button>
      `);
    }
  }

  async function handlePersonaAction(buttonEl) {
    const action = buttonEl.dataset.personaAction;
    if (action === "edit") {
      const personaId = buttonEl.dataset.personaId;
      const item = (state.pageData.lastPersonaItems || []).find((entry) => String(entry.persona_id || entry.id || entry.name) === String(personaId)) || {};
      const beginDialogs = JSON.stringify(item.begin_dialogs || [], null, 2);
      showModal("编辑人格", `
        <label class="config-field"><span><strong>人格 ID</strong></span><input id="modal-persona-id" value="${escapeAttr(personaId)}" disabled></label>
        <label class="config-field"><span><strong>名称</strong></span><input id="modal-persona-name" value="${escapeAttr(item.name || personaId || "")}"></label>
        <label class="config-field"><span><strong>系统提示词</strong></span><textarea id="modal-persona-prompt" rows="9">${escapeHtml(item.system_prompt || item.prompt || "")}</textarea></label>
        <label class="config-field"><span><strong>开场对话 JSON</strong></span><textarea id="modal-persona-dialogs" rows="6">${escapeHtml(beginDialogs)}</textarea></label>
        <button class="solid-button" type="button" id="modal-persona-save" data-persona-id="${escapeAttr(personaId)}">保存</button>
      `);
      return;
    }
    const body = {
      action,
      id: buttonEl.dataset.id,
      group_id: buttonEl.dataset.groupId,
      persona_id: buttonEl.dataset.personaId,
    };
    const result = await apiPost("persona/action", body);
    if (action === "backup_detail" || action === "export") {
      showModal(action === "export" ? "人格导出" : "备份详情", `<pre class="code-preview">${escapeHtml(JSON.stringify(result.persona || result.backup || result, null, 2))}</pre>`);
      return;
    }
    showToast(result.message || "操作完成", result.success ? "ok" : "error");
    state.pageData.persona = null;
    await loadPageData("persona-learning", { force: true });
  }

  async function handleContentAction(buttonEl) {
    const result = await apiPost("content/action", {
      action: buttonEl.dataset.contentAction,
      bucket: buttonEl.dataset.bucket,
      id: buttonEl.dataset.id,
    });
    showToast(result.message || "操作完成", result.success ? "ok" : "error");
    state.pageData.content = null;
    await loadPageData("content", { force: true });
  }

  function collectConfigPayload() {
    const payload = Object.fromEntries(state.dirtySettings.entries());
    qsa("[data-config-field]").forEach((field) => {
      const key = field.dataset.configField;
      const type = field.dataset.configType;
      let value;
      if (field.type === "checkbox") value = field.checked;
      else if (type === "int") value = Number.parseInt(field.value || "0", 10);
      else if (type === "float") value = Number.parseFloat(field.value || "0");
      else if (type === "list") {
        const raw = field.value.trim();
        try {
          value = raw.startsWith("[") ? JSON.parse(raw) : raw.split(/\n+/).map((line) => line.trim()).filter(Boolean);
        } catch (_) {
          value = raw.split(/\n+/).map((line) => line.trim()).filter(Boolean);
        }
      } else value = field.value;
      payload[key] = value;
    });
    return payload;
  }

  function bindEvents() {
    $("refresh-button")?.addEventListener("click", () => loadPageData(state.page, { force: true }));
    $("modal-close")?.addEventListener("click", closeModal);
    $("jargon-search-button")?.addEventListener("click", () => {
      Object.keys(state.pageData).filter((key) => key.startsWith("jargon:")).forEach((key) => delete state.pageData[key]);
      loadJargon(true);
    });
    $("copy-insight-context")?.addEventListener("click", async () => {
      const text = JSON.stringify(state.dashboard || {}, null, 2);
      try {
        await navigator.clipboard.writeText(text);
        showToast("巡检上下文已复制");
      } catch (_) {
        showModal("巡检上下文", `<pre class="code-preview">${escapeHtml(text)}</pre>`);
      }
    });
    $("relearn-button")?.addEventListener("click", async () => {
      const result = await apiPost("content/action", { action: "relearn", group_id: "default" });
      showToast(result.message || "重新学习已提交", result.success ? "ok" : "error");
    });
    $("graph-type")?.addEventListener("change", () => loadGraphs(true));
    $("config-save-button")?.addEventListener("click", async () => {
      const result = await apiPost("settings/action", { action: "save", config: collectConfigPayload() });
      showToast(result.message || "设置已保存", result.success ? "ok" : "error");
      state.pageData.settings = null;
      await loadPageData("settings", { force: true });
    });
    $("dependency-install-button")?.addEventListener("click", async () => {
      const installButton = $("dependency-install-button");
      const originalLabel = installButton?.textContent || "手动安装";
      const settings = state.pageData.settings || {};
      if (installButton) {
        installButton.disabled = true;
        installButton.classList.add("is-busy");
        installButton.textContent = "安装中";
      }
      setText("dependency-output", "正在调用 pip 安装依赖，请等待命令输出...");
      try {
        const result = await apiPost("settings/action", {
          action: "install_dependencies",
          manual_confirmed: true,
          source: settings.manual_dependency_source || "system_settings",
          tier: $("dependency-tier")?.value || "full",
          pip_mirror: $("pip-mirror-select")?.value || "default",
        });
        const detail = result.result || result;
        setText("dependency-output", detail.output || detail.message || result.message || "依赖安装任务结束");
        showToast(result.message || detail.message || "依赖安装任务结束", result.success !== false ? "ok" : "error");
      } catch (error) {
        const message = error.message || String(error);
        setText("dependency-output", message);
        showToast(message, "error");
      } finally {
        if (installButton) {
          installButton.disabled = false;
          installButton.classList.remove("is-busy");
          installButton.textContent = originalLabel;
        }
      }
    });
    $("maibot-preview-button")?.addEventListener("click", () => runMaiBotImportAction("maibot_preview"));
    $("maibot-import-button")?.addEventListener("click", () => runMaiBotImportAction("maibot_import"));

    document.addEventListener("click", async (event) => {
      const target = event.target.closest("[data-route-card],[data-refresh-page],[data-review-action],[data-batch-review-kind],[data-jargon-action],[data-style-action],[data-persona-action],[data-content-action],[data-settings-group]");
      if (!target) return;
      if (target.dataset.routeCard) navigateToPage(target.dataset.routeCard);
      if (target.dataset.refreshPage) loadPageData(target.dataset.refreshPage, { force: true });
      if (target.dataset.reviewAction) await handleReviewAction(target.dataset.kind, target.dataset.id, target.dataset.reviewAction);
      if (target.dataset.batchReviewKind) await handleBatchReviewAction(target.dataset.batchReviewKind, target.dataset.batchReviewAction || "approve");
      if (target.dataset.jargonAction) await handleJargonAction(target.dataset.jargonAction, target.dataset.id);
      if (target.dataset.styleAction) await handleStyleAction(target.dataset.styleAction, target.dataset.id);
      if (target.dataset.personaAction) await handlePersonaAction(target);
      if (target.dataset.contentAction) await handleContentAction(target);
      if (target.dataset.settingsGroup) {
        state.settingsGroup = target.dataset.settingsGroup;
        renderSettings(state.pageData.settings || {});
      }
    });

    document.addEventListener("change", (event) => {
      const field = event.target.closest("[data-config-field]");
      if (!field) return;
      state.dirtySettings.set(field.dataset.configField, field.type === "checkbox" ? field.checked : field.value);
    });

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("#modal-jargon-save");
      if (!save) return;
      const result = await apiPost("jargon/action", {
        action: "update",
        id: save.dataset.id,
        content: $("modal-jargon-content")?.value,
        meaning: $("modal-jargon-meaning")?.value,
      });
      closeModal();
      showToast(result.message || "黑话已更新", result.success ? "ok" : "error");
      state.pageData = {};
      await loadPageData("jargon-learning", { force: true });
    });

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("#modal-style-save");
      if (!save) return;
      const result = await apiPost("style/action", {
        action: "update",
        id: save.dataset.id,
        description: modalFieldValue("modal-style-description"),
        few_shots_content: modalFieldValue("modal-style-few-shots"),
        learned_patterns: parseModalJson("modal-style-patterns", []),
      });
      closeModal();
      showToast(result.message || "表达方式已更新", result.success ? "ok" : "error");
      state.pageData.style = null;
      state.pageData.lastStyleItems = [];
      await loadPageData("expression-learning", { force: true });
    });

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("#modal-persona-save");
      if (!save) return;
      const personaId = save.dataset.personaId;
      const result = await apiPost("persona/action", {
        action: "update",
        persona_id: personaId,
        persona: {
          persona_id: personaId,
          name: modalFieldValue("modal-persona-name"),
          system_prompt: modalFieldValue("modal-persona-prompt"),
          prompt: modalFieldValue("modal-persona-prompt"),
          begin_dialogs: parseModalJson("modal-persona-dialogs", []),
        },
      });
      closeModal();
      showToast(result.message || "人格已更新", result.success ? "ok" : "error");
      state.pageData.persona = null;
      state.pageData.lastPersonaItems = [];
      await loadPageData("persona-learning", { force: true });
    });

    qsa(".nav-item").forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        navigateToPage(item.dataset.page || "home");
      });
    });
    qsa("#content-tabs button").forEach((buttonEl) => {
      buttonEl.addEventListener("click", () => {
        state.contentType = buttonEl.dataset.contentType || "dialogues";
        renderContent(state.pageData.content || {});
      });
    });
    window.addEventListener("hashchange", () => navigateToPage(resolvePageFromHash(), { skipHash: true }));
  }

  function setThemeFromBridge() {
    try {
      const bridge = window.AstrBotPluginPage;
      const apply = (ctx) => {
        if (ctx && typeof ctx.isDark === "boolean") {
          document.documentElement.setAttribute("data-theme", ctx.isDark ? "dark" : "light");
        }
      };
      apply(bridge && bridge.getContext && bridge.getContext());
      if (bridge && bridge.onContextChange) bridge.onContextChange(apply);
      if (bridge && bridge.onContext) bridge.onContext(apply);
    } catch (_) {}
  }

  function initSpringMotion() {
    const stage = qs(".spring-stage");
    const canvas = $("physics-canvas");
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    if (!stage || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const resize = () => {
      const rect = stage.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * devicePixelRatio));
      canvas.height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);
    physics.particles = qsa(".spring-node:not(.node-core)", stage).map((el, index) => ({
      el, x: 0, y: 0, vx: 0, vy: 0, seed: index * 2.3,
    }));
    stage.addEventListener("pointermove", (event) => {
      const rect = stage.getBoundingClientRect();
      physics.pointer.x = event.clientX - rect.left;
      physics.pointer.y = event.clientY - rect.top;
      physics.pointer.active = true;
    });
    stage.addEventListener("pointerleave", () => { physics.pointer.active = false; });
    if (!physics.running) {
      physics.running = true;
      physics.last = performance.now();
      requestAnimationFrame(tickSpringMotion);
    }
  }

  function tickSpringMotion(now) {
    const stage = qs(".spring-stage");
    const canvas = $("physics-canvas");
    if (!stage || !canvas) return;
    const ctx = canvas.getContext("2d");
    const rect = stage.getBoundingClientRect();
    const dt = Math.min(0.033, Math.max(0.001, (now - physics.last) / 1000));
    physics.last = now;
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.strokeStyle = "rgba(65, 105, 225, 0.14)";
    ctx.lineWidth = 1.2;

    const core = { x: rect.width / 2, y: rect.height / 2 };
    physics.particles.forEach((point) => {
      const own = point.el.getBoundingClientRect();
      const baseX = own.left - rect.left + own.width / 2 - point.x;
      const baseY = own.top - rect.top + own.height / 2 - point.y;
      let targetX = Math.sin(now / 1350 + point.seed) * 6;
      let targetY = Math.cos(now / 1500 + point.seed) * 5;
      if (physics.pointer.active) {
        const cx = baseX + point.x;
        const cy = baseY + point.y;
        const dx = cx - physics.pointer.x;
        const dy = cy - physics.pointer.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const force = Math.max(0, 96 - dist) / 96;
        targetX += dx / dist * force * 18;
        targetY += dy / dist * force * 18;
      }
      point.vx += (targetX - point.x) * 28 * dt;
      point.vy += (targetY - point.y) * 28 * dt;
      point.vx *= Math.max(0, 1 - 14 * dt);
      point.vy *= Math.max(0, 1 - 14 * dt);
      point.x += point.vx * dt * 60;
      point.y += point.vy * dt * 60;
      const px = baseX + point.x;
      const py = baseY + point.y;
      ctx.beginPath();
      ctx.moveTo(core.x, core.y);
      ctx.quadraticCurveTo((core.x + px) / 2, (core.y + py) / 2 - 8, px, py);
      ctx.stroke();
      point.el.style.transform = `translate3d(${point.x.toFixed(2)}px, ${point.y.toFixed(2)}px, 0)`;
    });
    requestAnimationFrame(tickSpringMotion);
  }

  function startGraphRender() {
    const canvas = $("graph-canvas");
    if (!canvas) return;
    bindGraphCanvas(canvas);
    syncGraphCanvasSize(canvas, { force: true });
    if (!state.graph.running) {
      state.graph.running = true;
      requestAnimationFrame(tickGraph);
    }
  }

  function bindGraphCanvas(canvas) {
    if (state.graph.canvasBound) return;
    state.graph.canvasBound = true;

    canvas.addEventListener("pointerdown", (event) => {
      const point = graphPointer(event, canvas);
      const node = hitGraphNode(point.x, point.y);
      if (!node) return;
      event.preventDefault();
      canvas.setPointerCapture?.(event.pointerId);
      node.pinned = true;
      node.vx = 0;
      node.vy = 0;
      state.graph.dragged = {
        node,
        pointerId: event.pointerId,
        offsetX: node.x - point.x,
        offsetY: node.y - point.y,
      };
      canvas.classList.add("is-dragging");
    });

    canvas.addEventListener("pointermove", (event) => {
      const point = graphPointer(event, canvas);
      const drag = state.graph.dragged;
      if (drag && drag.pointerId === event.pointerId) {
        const min = graphNodeMargin(drag.node.radius || graphNodeRadius(drag.node));
        drag.node.x = clamp(point.x + drag.offsetX, min, state.graph.width - min);
        drag.node.y = clamp(point.y + drag.offsetY, min, state.graph.height - min);
        drag.node.homeX = drag.node.x;
        drag.node.homeY = drag.node.y;
        drag.node.vx = 0;
        drag.node.vy = 0;
        event.preventDefault();
        return;
      }
      state.graph.hovered = hitGraphNode(point.x, point.y);
      canvas.classList.toggle("has-hover", Boolean(state.graph.hovered));
    });

    const releaseDrag = (event) => {
      const drag = state.graph.dragged;
      if (drag && drag.pointerId === event.pointerId) {
        drag.node.vx = 0;
        drag.node.vy = 0;
        state.graph.dragged = null;
        canvas.classList.remove("is-dragging");
        canvas.releasePointerCapture?.(event.pointerId);
      }
    };
    canvas.addEventListener("pointerup", releaseDrag);
    canvas.addEventListener("pointercancel", releaseDrag);
    canvas.addEventListener("pointerleave", () => {
      state.graph.hovered = null;
      canvas.classList.remove("has-hover");
    });

    window.addEventListener("resize", () => {
      syncGraphCanvasSize(canvas, { force: true });
    });
  }

  function tickGraph() {
    const canvas = $("graph-canvas");
    if (!canvas) {
      state.graph.running = false;
      return;
    }
    const ctx = canvas.getContext("2d");
    const { width, height, ratio } = syncGraphCanvasSize(canvas);
    const nodes = state.graph.nodes;
    const links = state.graph.links;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const byId = new Map(nodes.map((node) => [String(node.id), node]));

    links.slice(0, 260).forEach((link) => {
      const source = byId.get(String(link.source));
      const target = byId.get(String(link.target));
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dist = Math.max(1, Math.hypot(dx, dy));
      const desired = Math.max(78, Math.min(132, Math.min(width, height) * 0.23));
      const force = (dist - desired) * GRAPH_LINK_STRENGTH;
      if (!source.pinned) {
        source.vx += (dx / dist) * force;
        source.vy += (dy / dist) * force;
      }
      if (!target.pinned) {
        target.vx -= (dx / dist) * force;
        target.vy -= (dy / dist) * force;
      }
      ctx.strokeStyle = "rgba(100, 116, 139, 0.28)";
      ctx.lineWidth = Math.max(1, Math.min(4, Number(link.value || 1)));
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();
    });

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < Math.min(nodes.length, i + 45); j += 1) {
        separateGraphNodes(nodes[i], nodes[j], 0.022);
      }
    }

    nodes.forEach((node, index) => {
      const cx = width / 2 + Math.sin(index) * 30;
      const cy = height / 2 + Math.cos(index) * 24;
      if (!node.pinned) {
        node.vx += ((node.homeX || cx) - node.x) * GRAPH_HOME_STRENGTH + (cx - node.x) * GRAPH_CENTER_STRENGTH;
        node.vy += ((node.homeY || cy) - node.y) * GRAPH_HOME_STRENGTH + (cy - node.y) * GRAPH_CENTER_STRENGTH;
        node.vx *= 0.74;
        node.vy *= 0.74;
        node.x += node.vx;
        node.y += node.vy;
      }
      const radius = node.radius || graphNodeRadius(node);
      if (clampGraphNode(node, width, height) && !node.pinned) {
        node.vx *= 0.12;
        node.vy *= 0.12;
      }
      const isHovered = state.graph.hovered === node || state.graph.dragged?.node === node;
      if (isHovered) {
        ctx.fillStyle = "rgba(15, 159, 143, 0.14)";
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 10, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = node.source === "livingmemory" ? "#0f9f8f" : index % 3 === 0 ? "#4169e1" : index % 3 === 1 ? "#d97706" : "#e11d48";
      ctx.beginPath();
      ctx.arc(node.x, node.y, isHovered ? radius + 2 : radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#162033";
      ctx.font = "12px system-ui";
      const label = String(node.name || node.label || "").slice(0, 12);
      const labelWidth = ctx.measureText(label).width;
      const labelX = clamp(node.x + radius + 4, 6, width - labelWidth - 6);
      const labelY = clamp(node.y + 4, 14, height - 6);
      ctx.fillText(label, labelX, labelY);
    });
    requestAnimationFrame(tickGraph);
  }

  function syncGraphCanvasSize(canvas, options = {}) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width || canvas.clientWidth || state.graph.width || 960));
    const height = Math.max(320, Math.floor(rect.height || canvas.clientHeight || state.graph.height || 520));
    const ratio = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const nextWidth = Math.floor(width * ratio);
    const nextHeight = Math.floor(height * ratio);
    const resized = canvas.width !== nextWidth || canvas.height !== nextHeight;
    if (resized || options.force) {
      const oldWidth = state.graph.width || width;
      const oldHeight = state.graph.height || height;
      canvas.width = nextWidth;
      canvas.height = nextHeight;
      state.graph.nodes.forEach((node, index) => {
        const radius = node.radius || graphNodeRadius(node);
        const min = graphNodeMargin(radius);
        const home = graphHomePosition(node.id, index, state.graph.nodes.length, width, height, radius);
        node.x = clamp((node.x / oldWidth) * width, min, width - min);
        node.y = clamp((node.y / oldHeight) * height, min, height - min);
        node.homeX = home.x;
        node.homeY = home.y;
        if (options.force && !node.pinned) {
          node.x = node.x * 0.55 + home.x * 0.45;
          node.y = node.y * 0.55 + home.y * 0.45;
        }
      });
    }
    state.graph.width = width;
    state.graph.height = height;
    return { width, height, ratio };
  }

  function graphPointer(event, canvas) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: clamp(event.clientX - rect.left, 0, state.graph.width || rect.width),
      y: clamp(event.clientY - rect.top, 0, state.graph.height || rect.height),
    };
  }

  function hitGraphNode(x, y) {
    for (let index = state.graph.nodes.length - 1; index >= 0; index -= 1) {
      const node = state.graph.nodes[index];
      const radius = (node.radius || graphNodeRadius(node)) + 8;
      if (Math.hypot(node.x - x, node.y - y) <= radius) {
        return node;
      }
    }
    return null;
  }

  function graphNodeRadius(node) {
    const raw = Number(node.symbolSize || node.value || node.weight || 12);
    return Math.max(9, Math.min(24, Number.isFinite(raw) ? raw : 12));
  }

  function graphNodeMargin(radius) {
    return Math.max(52, radius + GRAPH_SAFE_PADDING);
  }

  function clampGraphNode(node, width, height) {
    const radius = node.radius || graphNodeRadius(node);
    const min = graphNodeMargin(radius);
    const nextX = clamp(node.x, min, width - min);
    const nextY = clamp(node.y, min, height - min);
    const clamped = nextX !== node.x || nextY !== node.y;
    node.x = nextX;
    node.y = nextY;
    return clamped;
  }

  function separateGraphNodes(a, b, strength) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.max(1, Math.hypot(dx, dy));
    const minDist = (a.radius || graphNodeRadius(a)) + (b.radius || graphNodeRadius(b)) + 20;
    if (dist >= minDist) return;
    const shift = (minDist - dist) / minDist * strength;
    const nx = dx / dist;
    const ny = dy / dist;
    if (!a.pinned) {
      a.vx -= nx * shift;
      a.vy -= ny * shift;
      a.x -= nx * shift * 6;
      a.y -= ny * shift * 6;
    }
    if (!b.pinned) {
      b.vx += nx * shift;
      b.vy += ny * shift;
      b.x += nx * shift * 6;
      b.y += ny * shift * 6;
    }
  }

  function graphStableSeed(value) {
    let hash = 0;
    const text = String(value || "");
    for (let index = 0; index < text.length; index += 1) {
      hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
    }
    return hash % 997;
  }

  function graphValueKey(value) {
    if (value && typeof value === "object") {
      return String(value.id ?? value.name ?? value.label ?? "");
    }
    return String(value ?? "");
  }

  function clamp(value, min, max) {
    if (max < min) return min;
    return Math.max(min, Math.min(max, value));
  }

  async function init() {
    setThemeFromBridge();
    bindEvents();
    initSpringMotion();
    try {
      await bridgeReady();
      navigateToPage(resolvePageFromHash(), { skipHash: true, force: true });
    } catch (error) {
      showToast(error.message || String(error), "error");
      setText("runtime-status", "桥接失败");
      setText("runtime-summary", error.message || String(error));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
