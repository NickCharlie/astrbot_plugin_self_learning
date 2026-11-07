(() => {
  "use strict";

  const PAGE_META = {
    home: ["page.home.kicker", "page.home.title", "Dashboard", "学习模块控制台"],
    overview: ["page.overview.kicker", "page.overview.title", "Overview", "总览"],
    insights: ["page.insights.kicker", "page.insights.title", "Insights", "AI 巡检"],
    monitoring: ["page.monitoring.kicker", "page.monitoring.title", "Monitoring", "运行监控"],
    reviews: ["page.reviews.kicker", "page.reviews.title", "Reviews", "审查队列"],
    "jargon-learning": ["page.jargon.kicker", "page.jargon.title", "Jargon", "黑话学习"],
    "expression-learning": ["page.style.kicker", "page.style.title", "Expression", "表达方式学习"],
    "persona-learning": ["page.persona.kicker", "page.persona.title", "Persona", "人格学习"],
    "shadow-mode": ["page.shadow.kicker", "page.shadow.title", "Shadow", "影子模式"],
    emotion: ["page.emotion.kicker", "page.emotion.title", "Emotion", "情绪中枢"],
    content: ["page.content.kicker", "page.content.title", "Content", "学习内容"],
    graphs: ["page.graphs.kicker", "page.graphs.title", "Graphs", "图谱"],
    integrations: ["page.integrations.kicker", "page.integrations.title", "Integrations", "功能融合"],
    settings: ["page.settings.kicker", "page.settings.title", "Settings", "设置"],
  };
  const I18N_ROOT = "pages.dashboard";
  const GRAPH_SAFE_PADDING = 34;
  const GRAPH_HOME_STRENGTH = 0.0064;
  const GRAPH_CENTER_STRENGTH = 0.00016;
  const GRAPH_LINK_STRENGTH = 0.000035;

  const state = {
    page: "home",
    ready: false,
    dashboard: null,
    dashboardToken: 0,
    dashboardLoading: false,
    overview: null,
    pageData: {},
    selectedReviews: {
      persona: new Set(),
      style: new Set(),
      jargon: new Set(),
    },
    selectedJargon: new Set(),
    reviewParams: {},
    reviewBatchPage: 1,
    reviewBatchPages: 1,
    jargon: {
      page: 1,
      totalPages: 1,
      items: [],
      editingId: null,
      draft: { content: "", meaning: "" },
    },
    styleBucket: "dialogues",
    contentType: "dialogues",
    contentQuery: "",
    settingsGroup: null,
    dirtySettings: new Map(),
    shadow: {
      source: "live",
      groupId: "",
      targetGroupId: "",
      selectedId: "",
      minimumSamples: 3,
      profiles: [],
      candidates: [],
      statusData: null,
      initialized: false,
    },
    qchatPreviewData: null,
    qchatShadowSender: "",
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
  // 读取主题 CSS 变量（canvas 无法直接用 var()，逐帧读取跟随主题切换）
  const cssVar = (name, fallback) => {
    try {
      const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return value || fallback;
    } catch {
      return fallback;
    }
  };

  function locale() {
    try {
      const bridge = window.AstrBotPluginPage;
      return bridge?.getLocale?.() || bridge?.getContext?.()?.locale || document.documentElement.lang || "zh-CN";
    } catch (_) {
      return document.documentElement.lang || "zh-CN";
    }
  }

  function t(key, fallback = "") {
    const fullKey = key.startsWith("pages.") || key.startsWith("metadata.") || key.startsWith("config.")
      ? key
      : `${I18N_ROOT}.${key}`;
    try {
      const bridge = window.AstrBotPluginPage;
      const value = bridge?.t?.(fullKey, fallback);
      if (value !== undefined && value !== null && value !== fullKey) return String(value);
    } catch (_) {}
    return String(fallback || "");
  }

  function configT(path, fallback = "") {
    return t(`config.${path}`, fallback);
  }

  function applyStaticI18n(root = document) {
    document.documentElement.lang = locale();
    qsa("[data-i18n]", root).forEach((el) => {
      el.textContent = t(el.dataset.i18n, el.textContent);
    });
    qsa("[data-i18n-title]", root).forEach((el) => {
      el.setAttribute("title", t(el.dataset.i18nTitle, el.getAttribute("title") || ""));
    });
    qsa("[data-i18n-aria-label]", root).forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel, el.getAttribute("aria-label") || ""));
    });
    qsa("[data-i18n-placeholder]", root).forEach((el) => {
      el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder, el.getAttribute("placeholder") || ""));
    });
  }

  function endpoint(path) {
    return `page/${String(path || "").replace(/^\/+/, "").replace(/\/+/g, "/")}`;
  }

  async function bridgeReady() {
    const bridge = window.AstrBotPluginPage;
    if (!bridge) {
      throw new Error(t("errors.bridgeMissing", "AstrBot 插件页桥接 SDK 未加载"));
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
      throw new Error(body.message || t("errors.requestFailed", "请求失败"));
    }
    if (body && body.success === false) {
      throw new Error(body.message || body.error || t("errors.requestFailed", "请求失败"));
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
    return new Intl.NumberFormat(locale(), { maximumFractionDigits: digits }).format(num);
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

  function empty(text = t("empty.default", "暂无数据")) {
    return `<div class="empty-state">${escapeHtml(text)}</div>`;
  }

  function pill(text, tone = "") {
    return `<span class="mini-badge ${escapeAttr(tone)}">${escapeHtml(text)}</span>`;
  }

  function button(label, attrs = "", cls = "ghost-button") {
    return `<button class="${cls}" type="button" ${attrs}>${escapeHtml(label)}</button>`;
  }

  function normalizeId(id) {
    return String(id ?? "").trim();
  }

  function selectedReviewSet(kind) {
    if (!state.selectedReviews[kind]) state.selectedReviews[kind] = new Set();
    return state.selectedReviews[kind];
  }

  function selectedReviewIds(kind) {
    return Array.from(selectedReviewSet(kind)).filter(Boolean);
  }

  function isReviewSelected(kind, id) {
    return selectedReviewSet(kind).has(normalizeId(id));
  }

  function isJargonSelected(id) {
    return state.selectedJargon.has(normalizeId(id));
  }

  function pruneSelection(selection, validIds) {
    const valid = new Set((validIds || []).map(normalizeId).filter(Boolean));
    Array.from(selection).forEach((id) => {
      if (!valid.has(id)) selection.delete(id);
    });
  }

  function reviewCheckbox(kind, id) {
    const safeId = normalizeId(id);
    const label = escapeAttr(t("actions.select", "选择"));
    return `<label class="select-cell" title="${label}">
      <input type="checkbox" aria-label="${label}" data-review-select-kind="${escapeAttr(kind)}" data-review-select-id="${escapeAttr(safeId)}" ${isReviewSelected(kind, safeId) ? "checked" : ""}>
    </label>`;
  }

  function jargonCheckbox(id) {
    const safeId = normalizeId(id);
    const label = escapeAttr(t("actions.select", "选择"));
    return `<label class="select-cell" title="${label}">
      <input type="checkbox" aria-label="${label}" data-jargon-select-id="${escapeAttr(safeId)}" ${isJargonSelected(safeId) ? "checked" : ""}>
    </label>`;
  }

  function reviewCountText(kind, total) {
    const selected = selectedReviewIds(kind).length;
    return selected ? `${fmt(selected, 0)}/${fmt(total, 0)}` : fmt(total, 0);
  }

  // 审查队列三栏数据源（与独立版 ReviewsPage 同口径）：人格栏排除风格审查；风格栏优先取
  // 人格待审中 review_source === "style_learning" 的记录、缺失时回退到风格审查列表；
  // 任一栏带搜索词时风格栏直接取风格审查列表（服务端按风格搜索词过滤）。
  function reviewQueueItems(kind, data = state.pageData.reviews || {}) {
    const personaAll = listOf(data.persona_pending).filter(isRecord);
    if (kind === "persona") return personaAll.filter((item) => item.review_source !== "style_learning");
    if (kind === "style") {
      const params = state.reviewParams || {};
      const fromPersona = personaAll.filter((item) => item.review_source === "style_learning");
      const fromStyle = listOf(data.style_reviews).filter(isRecord);
      if (params.persona_keyword || params.style_keyword) return fromStyle;
      return fromPersona.length ? fromPersona : fromStyle;
    }
    if (kind === "jargon") return listOf(data.jargon_pending).filter(isRecord);
    return [];
  }

  function visibleReviewIds(kind) {
    return reviewQueueItems(kind).map((item) => normalizeId(item.id)).filter(Boolean);
  }

  function jargonPageIds() {
    return (state.jargon.items || [])
      .map((item) => normalizeId(item.id))
      .filter(Boolean);
  }

  function reviewSearchParams() {
    const params = { limit: 50 };
    const personaKeyword = $("persona-review-keyword")?.value?.trim() || "";
    const styleKeyword = $("style-review-keyword")?.value?.trim() || "";
    const jargonKeyword = $("jargon-review-keyword")?.value?.trim() || "";
    if (personaKeyword) params.persona_keyword = personaKeyword;
    if (styleKeyword) params.style_keyword = styleKeyword;
    if (jargonKeyword) params.jargon_keyword = jargonKeyword;
    return params;
  }

  function clearCached(prefix) {
    Object.keys(state.pageData)
      .filter((key) => key === prefix || key.startsWith(`${prefix}:`))
      .forEach((key) => delete state.pageData[key]);
  }

  // 批量按钮：未勾选时作用于当前列出的全部记录（全部通过 / 驳回 / 删除），勾选后只作用于选中项
  function reviewBatchLabel(action, scoped) {
    if (action === "approve") return scoped ? t("reviews.batch.approveSelected", "通过所选") : t("reviews.batch.approveAll", "全部通过");
    if (action === "reject") return scoped ? t("reviews.batch.rejectSelected", "驳回所选") : t("reviews.batch.rejectAll", "全部驳回");
    return scoped ? t("reviews.batch.deleteSelected", "删除所选") : t("reviews.batch.deleteAll", "全部删除");
  }

  function refreshSelectionLabels() {
    ["persona", "style", "jargon"].forEach((kind) => {
      const ids = visibleReviewIds(kind);
      setText(`${kind}-review-count`, reviewCountText(kind, ids.length));
      const scoped = selectedReviewIds(kind).length > 0;
      qsa(`[data-batch-review-kind="${kind}"]`).forEach((buttonEl) => {
        buttonEl.textContent = reviewBatchLabel(buttonEl.dataset.batchReviewAction, scoped);
      });
    });
    const selectedJargon = Array.from(state.selectedJargon).filter(Boolean).length;
    const visibleJargon = jargonPageIds().length;
    setText("jargon-selection-count", t("selection.selectedOfTotal", "已选 {selected}/{total}")
      .replace("{selected}", fmt(selectedJargon, 0))
      .replace("{total}", fmt(visibleJargon, 0)));
  }

  function setBusy(label = t("status.loading", "加载中")) {
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
    close.setAttribute("aria-label", t("actions.closeToast", "关闭提示"));
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

  function warningListHtml(warnings) {
    const items = Array.isArray(warnings)
      ? warnings
          .map((message) => String(message).trim())
          .filter(Boolean)
      : [];
    return items.map((message) => `
      <div class="settings-warning">
        <strong>成本提醒</strong>
        <span>${escapeHtml(message)}</span>
      </div>
    `).join("");
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

  // tone 与独立版 ConfirmDialog 的确认按钮色调一致：danger（默认）/ success / warning
  function showConfirm(title, message, confirmText = t("actions.confirm", "确认"), tone = "danger") {
    return new Promise((resolve) => {
      const confirmClass = tone === "success" ? "ghost-button success-button"
        : tone === "warning" ? "ghost-button warning-button" : "danger-button";
      const html = `
        <p>${escapeHtml(message)}</p>
        <div class="inline-actions">
          <button class="ghost-button" type="button" id="modal-confirm-cancel">${escapeHtml(t("actions.cancel", "取消"))}</button>
          <button class="${confirmClass}" type="button" id="modal-confirm-ok">${escapeHtml(confirmText)}</button>
        </div>
      `;
      showModal(title, html);
      const ok = $("modal-confirm-ok");
      const cancel = $("modal-confirm-cancel");
      const modal = $("detail-modal");
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        closeModal();
        resolve(value);
      };
      ok?.addEventListener("click", () => finish(true), { once: true });
      cancel?.addEventListener("click", () => finish(false), { once: true });
      modal?.addEventListener("cancel", () => finish(false), { once: true });
      modal?.addEventListener("close", () => finish(false), { once: true });
    });
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
    setText("page-kicker", t(meta[0], meta[2]));
    setText("page-title", t(meta[1], meta[3]));
    loadPageData(next, { force: !!options.force });
  }

  async function loadDashboard(force = false, options = {}) {
    if (state.dashboard && !force) {
      renderDashboard(state.dashboard);
      return state.dashboard;
    }
    // 静默刷新（60s 定时）不切换加载态、不弹错误提示；并发时只采用最后一次发起的结果
    const quiet = !!options.quiet;
    const token = ++state.dashboardToken;
    if (!quiet) {
      state.dashboardLoading = true;
      setBusy(t("status.syncing", "同步中"));
      renderSystemEntries(state.dashboard || {});
    }
    try {
      const data = await apiGet("dashboard");
      if (token !== state.dashboardToken) return state.dashboard;
      state.dashboardLoading = false;
      state.dashboard = data;
      state.overview = data.overview || data;
      renderDashboard(data);
      return data;
    } catch (error) {
      if (token !== state.dashboardToken) return state.dashboard;
      state.dashboardLoading = false;
      renderSystemEntries(state.dashboard || {});
      if (quiet) return state.dashboard;
      showToast(error.message || String(error), "error");
      showErrors({ bridge: error.message || String(error) });
      throw error;
    }
  }

  async function loadPageData(page, options = {}) {
    const force = !!options.force;
    try {
      // 首页 / AI 巡检 / 运行监控与独立版一样共用同一份 Dashboard 快照
      if (page === "home" || page === "insights" || page === "monitoring") {
        await loadDashboard(force);
        return;
      }
      if (page === "overview") return renderOverview(await loadDashboard(force));
      if (page === "emotion") return loadEmotion(force);
      if (page === "reviews") return await loadReviews(force);
      if (page === "jargon-learning") return await loadJargon(force);
      if (page === "expression-learning") return await loadStyle(force);
      if (page === "persona-learning") return await loadPersona(force);
      if (page === "shadow-mode") return await loadShadowMode(force);
      if (page === "content") return await loadContent(force);
      if (page === "graphs") return loadGraphs(force);
      if (page === "integrations") return renderIntegrations(await cached("integrations", () => apiGet("integrations"), force));
      if (page === "settings") {
        if (force) state.dirtySettings.clear();
        return renderSettings(await cached("settings", () => apiGet("settings", { schema: "true" }), force));
      }
    } catch (error) {
      showToast(error.message || String(error), "error");
    }
  }

  async function cached(key, loader, force) {
    if (!force && state.pageData[key]) return state.pageData[key];
    setBusy(t("status.loading", "加载中"));
    let data;
    try {
      data = await loader();
    } finally {
      // 加载结束（成功或失败）复位为最近一次确定状态，避免非快照页徽标永远停在"加载中"
      setBusy(state.runtimeStatusLabel || t("status.connected", "已连接"));
    }
    state.pageData[key] = data;
    if (key.startsWith("reviews:")) state.pageData.reviews = data;
    return data;
  }

  function renderDashboard(data) {
    const overview = data.overview || data;
    const runtime = overview.runtime || {};
    const webui = overview.webui || {};
    const errors = data.errors || overview.errors || {};
    const degraded = runtime.database_degraded || Object.keys(errors).length > 0;

    // 桥接连接状态：侧栏运行状态 + 首页 hero 次要信息行（iframe 专属）
    const statusLabel = degraded ? t("status.partial", "部分可用") : t("status.healthy", "运行正常");
    state.runtimeStatusLabel = statusLabel;
    const resolvedDashboardUrl = resolveHostUrl(webui.dashboard_url || "");
    const summary = degraded
      ? t("status.degradedSummary", "嵌入式页面已载入，部分服务处于降级状态。")
      : t("status.connectedSummary", "已连接官方插件页 API，独立 WebUI: {url}")
        .replace("{url}", resolvedDashboardUrl || t("status.notConfigured", "未配置"));
    setText("runtime-status", statusLabel);
    setText("hero-status", statusLabel);
    setText("runtime-summary", summary);
    setText("hero-summary", summary);
    $("runtime-status")?.classList.toggle("warn", degraded);
    $("hero-status")?.classList.toggle("warn", degraded);

    const fullLink = $("full-dashboard-link");
    if (fullLink && resolvedDashboardUrl) fullLink.href = resolvedDashboardUrl;

    // 首页 / AI 巡检 / 运行监控与独立版一样由同一份快照驱动
    renderHome(data);
    renderInsights(data);
    renderMonitoring(data);
    showErrors(errors);
  }

  // ── 与独立版 lib/format.ts / pages/shared.ts 同口径的读数工具 ──
  function safeNum(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function fmtPercent(value) {
    return `${Math.max(0, Math.min(100, safeNum(value))).toFixed(0)}%`;
  }

  function textOrDash(value) {
    return value === null || value === undefined || value === "" ? "--" : String(value);
  }

  function isRecord(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function listOf(value) {
    if (Array.isArray(value)) return value;
    const record = isRecord(value) ? value : {};
    for (const key of ["items", "data", "results", "updates", "reviews", "backups", "batches", "dashboards", "jargon_list"]) {
      if (Array.isArray(record[key])) return record[key];
    }
    return [];
  }

  // 独立版 Badge tone → 内嵌 mini-badge 修饰类
  function toneClass(tone) {
    return tone === "success" ? "ok" : tone === "warning" ? "warn" : tone === "danger" ? "danger" : "";
  }

  // 健康检查等明细对象：前 3 项 key: value，以 · 连接（与独立版 detailText 同口径）
  function detailText(value) {
    if (value === null || value === undefined || value === "") return "--";
    if (typeof value !== "object") return String(value);
    const entries = Object.entries(value).slice(0, 3);
    if (!entries.length) return "--";
    return entries
      .map(([key, item]) => `${key}: ${item !== null && typeof item === "object" ? JSON.stringify(item) : String(item)}`)
      .join(" · ");
  }

  // 黑话待审：读待审接口分页 total（列表被 limit 截断）；待审段读取失败时退回 stats 估算，
  // 避免误报「队列已清空」（与独立版 jargonPendingTotal 同口径）
  function jargonPendingTotal(data) {
    const reviews = data.reviews || {};
    const failed = Boolean((reviews.errors || {}).jargon_pending);
    const payload = failed ? {} : reviews.jargon_pending;
    if (Array.isArray(payload)) return payload.length;
    const envelope = isRecord(payload) ? payload : {};
    const total = envelope.total;
    if (total !== undefined && total !== null && total !== "") return safeNum(total);
    const rows = listOf(payload);
    if (rows.length || Object.keys(envelope).length) return rows.length;
    const stats = (data.overview || {}).jargon || {};
    const nested = stats.data || {};
    return Math.max(0, safeNum(stats.total_candidates ?? nested.total_candidates) - safeNum(stats.confirmed_jargon ?? nested.confirmed_jargon));
  }

  // 待办总量：人格待审 + 风格待审 + 黑话待审（分页 total）；人格首屏混入风格审查时扣除
  // 风格部分避免重复计数。首页与 AI 巡检同源（与独立版 reviewBacklog 同口径）
  function reviewBacklog(data) {
    const reviews = data.reviews || {};
    const personaPayload = reviews.persona_pending;
    const stylePayload = reviews.style_reviews;
    const personaItems = listOf(personaPayload);
    const personaTotal = safeNum((isRecord(personaPayload) ? personaPayload : {}).total, personaItems.length);
    const styleTotal = safeNum((isRecord(stylePayload) ? stylePayload : {}).total, listOf(stylePayload).length);
    const personaIncludesStyle = personaItems.some((item) => isRecord(item) && item.review_source === "style_learning");
    const personaPending = personaIncludesStyle ? Math.max(0, personaTotal - styleTotal) : personaTotal;
    const jargonPending = jargonPendingTotal(data);
    return { personaPending, styleTotal, jargonPending, total: personaPending + styleTotal + jargonPending };
  }

  // 智能指标综合评分（0-100）与参与评估的维度数
  function intelligenceScore(data) {
    const intelligence = (data.metrics || {}).intelligence || (data.overview || {}).metrics || {};
    return {
      score: normalizeScore(intelligence.overall_score),
      dimensions: isRecord(intelligence.dimensions) ? Object.keys(intelligence.dimensions).length : 0,
    };
  }

  // ── 首页（对齐独立版 HomePage：hero + 快捷坞 + 4 读数 + 学习模块 + 系统入口） ──
  // 快捷入口与学习模块与独立版同序同文案；独立版图标为 Material Icons，iframe 内不加载图标字体。
  function homeQuickLinks() {
    return [
      { page: "jargon-learning", label: t("home.quick.jargon", "黑话") },
      { page: "expression-learning", label: t("home.quick.expression", "表达") },
      { page: "persona-learning", label: t("home.quick.persona", "人格") },
      { page: "shadow-mode", label: t("home.quick.shadow", "影子") },
      { page: "reviews", label: t("home.quick.reviews", "审查") },
      { page: "content", label: t("home.quick.content", "内容") },
      { page: "monitoring", label: t("home.quick.monitoring", "监控") },
    ];
  }

  function homeModules() {
    return [
      { page: "jargon-learning", title: t("home.modules.jargonTitle", "黑话学习"), description: t("home.modules.jargonDesc", "群聊词汇、语义和确认队列") },
      { page: "expression-learning", title: t("home.modules.styleTitle", "表达方式学习"), description: t("home.modules.styleDesc", "对话样本、风格特征与学习记录") },
      { page: "persona-learning", title: t("home.modules.personaTitle", "人格学习"), description: t("home.modules.personaDesc", "当前人格、演化建议与备份") },
      { page: "shadow-mode", title: t("home.modules.shadowTitle", "影子模式"), description: t("home.modules.shadowDesc", "选择群友并学习其表达习惯") },
    ];
  }

  // 与独立版 HomePage snapshot 同口径
  function homeSnapshot(data) {
    const overview = data.overview || {};
    const metrics = data.metrics || {};
    const health = (data.monitoring || {}).health || {};
    const trends = metrics.trends || {};
    const jargon = overview.jargon || {};
    const jargonNested = jargon.data || {};
    const statsRaw = data.data_statistics || {};
    const statistics = isRecord(statsRaw.data ?? statsRaw) ? (statsRaw.data ?? statsRaw) : {};
    const backlog = reviewBacklog(data);
    const integrations = listOf((data.integrations || {}).dashboards ?? data.integrations);
    const totalMessages = safeNum(metrics.total_messages_collected);
    const filtered = safeNum(metrics.filtered_messages);
    const llmSummary = metrics.llm_call_summary || {};
    const llmAbnormal = safeNum(llmSummary.abnormal_provider_count);
    return {
      health,
      totalMessages,
      filterRate: totalMessages ? filtered / totalMessages * 100 : 0,
      learningEfficiency: safeNum(metrics.learning_efficiency),
      backlog: backlog.total,
      personaPending: backlog.personaPending,
      styleTotal: backlog.styleTotal,
      jargonPending: backlog.jargonPending,
      batches: listOf(trends.recent_batches).length,
      jargonCandidates: safeNum(jargon.total_candidates ?? jargonNested.total_candidates),
      jargonConfirmed: safeNum(jargon.confirmed_jargon ?? jargonNested.confirmed_jargon),
      contentCount: safeNum(statistics.style_learning),
      graphNodes: safeNum(statistics.memory) + safeNum(statistics.knowledge_graph),
      integrations,
      activeIntegrations: integrations.filter((item) => isRecord(item) && item.active).length,
      delegatedIntegrations: integrations.filter((item) => isRecord(item) && item.delegated).length,
      memory: integrations.find((item) => isRecord(item) && item.id === "livingmemory") || {},
      llmCalls: safeNum(llmSummary.total_calls),
      llmAbnormal,
      insightTone: health.overall !== "healthy" || llmAbnormal > 0 ? "danger" : backlog.total > 20 ? "warning" : "success",
      backups: listOf((overview.persona_backups || {}).backups).length,
    };
  }

  function renderHome(data) {
    const snap = homeSnapshot(data);
    const count = (value) => fmt(value, 0);
    setHtml("quick-actions", homeQuickLinks().map((item) => `
      <a class="quick-entry" href="#/${escapeAttr(item.page)}" data-route-card="${escapeAttr(item.page)}">${escapeHtml(item.label)}</a>
    `).join(""));
    setText("home-pulse-efficiency", fmtPercent(snap.learningEfficiency));
    setText("home-pulse-backlog", count(snap.backlog));
    setText("home-pulse-content", snap.contentCount ? count(snap.contentCount) : "--");
    setText("home-pulse-batches", count(snap.batches));

    const notes = {
      "jargon-learning": t("home.modules.jargonNote", "候选 {candidates} · 已确认 {confirmed}")
        .replace("{candidates}", count(snap.jargonCandidates))
        .replace("{confirmed}", count(snap.jargonConfirmed)),
      "expression-learning": t("home.modules.styleNote", "内容 {content} · 待审 {pending}")
        .replace("{content}", count(snap.contentCount))
        .replace("{pending}", count(snap.styleTotal)),
      "persona-learning": t("home.modules.personaNote", "待审 {pending} · 备份 {backups}")
        .replace("{pending}", count(snap.personaPending))
        .replace("{backups}", count(snap.backups)),
      "shadow-mode": t("home.modules.shadowNote", "现有群聊与导入记录均可学习"),
    };
    setHtml("module-card-grid", homeModules().map((item) => `
      <a class="module-card learning-module-card" href="#/${escapeAttr(item.page)}" data-route-card="${escapeAttr(item.page)}">
        <span class="module-card-head">
          <strong>${escapeHtml(item.title)}</strong>
          <span class="card-arrow" aria-hidden="true">→</span>
        </span>
        <span class="card-desc">${escapeHtml(item.description)}</span>
        <small class="card-note">${escapeHtml(notes[item.page] || "")}</small>
      </a>
    `).join(""));
    renderSystemEntries(data);
  }

  // 系统入口卡（与独立版 HomePage entries 同序、同文案、同判定）
  function systemEntries(data) {
    const s = homeSnapshot(data);
    const count = (value) => fmt(value, 0);
    const health = String(s.health.overall || "unknown");
    return [
      {
        page: "overview",
        title: t("home.entries.overviewTitle", "总览"),
        description: t("home.entries.overviewDesc", "核心指标与消息趋势"),
        value: fmtPercent(s.learningEfficiency),
        note: t("home.entries.overviewNote", "{messages} 条消息 · 筛选率 {rate}")
          .replace("{messages}", count(s.totalMessages))
          .replace("{rate}", fmtPercent(s.filterRate)),
        status: t("home.entries.overviewStatus", "数据已同步"),
        tone: s.totalMessages > 0 ? "success" : "warning",
      },
      {
        page: "insights",
        title: t("home.entries.insightsTitle", "AI 巡检"),
        description: t("home.entries.insightsDesc", "异常、瓶颈与下一步建议"),
        value: s.insightTone === "danger"
          ? t("home.entries.insightsAttention", "需关注")
          : s.insightTone === "warning" ? t("home.entries.insightsBacklog", "有积压") : t("home.entries.insightsNormal", "正常"),
        note: t("home.entries.insightsNote", "{backlog} 项待办 · {abnormal} 个模型异常")
          .replace("{backlog}", count(s.backlog))
          .replace("{abnormal}", count(s.llmAbnormal)),
        status: s.insightTone === "success" ? t("home.entries.insightsClear", "暂无高优先级问题") : t("home.entries.insightsReview", "建议查看"),
        tone: s.insightTone,
      },
      {
        page: "monitoring",
        title: t("home.entries.monitoringTitle", "运行监控"),
        description: t("home.entries.monitoringDesc", "健康状态、热点与模型调用"),
        value: health,
        note: t("home.entries.monitoringNote", "{calls} 次模型调用 · {abnormal} 个异常")
          .replace("{calls}", count(s.llmCalls))
          .replace("{abnormal}", count(s.llmAbnormal)),
        status: health === "healthy" ? t("home.entries.monitoringHealthy", "系统健康") : t("home.entries.monitoringUnhealthy", "健康检查异常"),
        tone: health === "healthy" ? "success" : "danger",
      },
      {
        page: "reviews",
        title: t("home.entries.reviewsTitle", "审查队列"),
        description: t("home.entries.reviewsDesc", "人格、风格、黑话与批次"),
        value: count(s.backlog),
        note: t("home.entries.reviewsNote", "人格 {persona} · 风格 {style} · 黑话 {jargon}")
          .replace("{persona}", count(s.personaPending))
          .replace("{style}", count(s.styleTotal))
          .replace("{jargon}", count(s.jargonPending)),
        status: s.backlog ? t("home.entries.reviewsPending", "等待处理") : t("home.entries.reviewsClear", "队列已清空"),
        tone: s.backlog > 20 ? "warning" : "success",
      },
      {
        page: "content",
        title: t("home.entries.contentTitle", "学习内容"),
        description: t("home.entries.contentDesc", "对话、分析、表达模式与历史"),
        value: s.contentCount ? count(s.contentCount) : "--",
        note: t("home.entries.contentNote", "当前表达学习内容总量"),
        status: s.contentCount ? t("home.entries.contentReady", "内容可浏览") : t("home.entries.contentEmpty", "暂无内容"),
        tone: s.contentCount ? "success" : "default",
      },
      {
        page: "graphs",
        title: t("home.entries.graphsTitle", "记忆 / 知识图谱"),
        description: t("home.entries.graphsDesc", "本地图谱与记忆后端"),
        value: s.graphNodes ? count(s.graphNodes) : s.memory.active ? t("home.entries.graphsBackend", "后端") : "--",
        note: s.graphNodes
          ? t("home.entries.graphsNodesNote", "个当前记忆图谱节点")
          : s.memory.delegated ? t("home.entries.graphsDelegatedNote", "读取 LivingMemory 后端") : t("home.entries.graphsLocalNote", "本地图谱"),
        status: s.graphNodes || s.memory.active ? t("home.entries.graphsAvailable", "可用") : t("home.entries.graphsEmpty", "暂无节点"),
        tone: s.graphNodes || s.memory.active ? "success" : "default",
      },
      {
        page: "integrations",
        title: t("home.entries.integrationsTitle", "功能融合"),
        description: t("home.entries.integrationsDesc", "插件分工与伴随插件运行状态"),
        value: s.integrations.length ? `${s.activeIntegrations}/${s.integrations.length}` : "--",
        note: s.delegatedIntegrations
          ? t("home.entries.integrationsDelegated", "{count} 项已委托").replace("{count}", String(s.delegatedIntegrations))
          : t("home.entries.integrationsApi", "插件 API 入口"),
        status: s.activeIntegrations ? t("home.entries.integrationsConnected", "已连接") : t("home.entries.integrationsSolo", "仅本插件在线"),
        tone: s.activeIntegrations ? "success" : "warning",
      },
      {
        page: "integrations",
        title: t("home.entries.importsTitle", "世界书 / QQ 导入"),
        description: t("home.entries.importsDesc", "预览、导入和结果统计"),
        value: "API",
        note: t("home.entries.importsNote", "世界书与聊天记录导入接口"),
        status: s.integrations.length ? t("home.entries.importsAvailable", "可用") : t("home.entries.importsWaiting", "等待融合状态"),
        tone: s.integrations.length ? "success" : "default",
      },
    ];
  }

  // 加载中（非静默刷新）与独立版一致：隐藏状态徽标，读数显示 -- / 加载中...
  function renderSystemEntries(data) {
    const loading = state.dashboardLoading;
    setHtml("system-entry-grid", systemEntries(data || {}).map((entry) => `
      <a class="module-card entry-card" href="#/${escapeAttr(entry.page)}" data-route-card="${escapeAttr(entry.page)}">
        <span class="module-card-head">
          <strong>${escapeHtml(entry.title)}</strong>
          ${loading ? "" : pill(entry.status, toneClass(entry.tone))}
        </span>
        <span class="card-desc">${escapeHtml(entry.description)}</span>
        <span class="entry-state">
          <strong>${escapeHtml(loading ? "--" : entry.value)}</strong>
          <span>${escapeHtml(loading ? t("home.entries.loading", "加载中...") : entry.note)}</span>
        </span>
      </a>
    `).join(""));
  }

  // ── AI 巡检：与独立版 pages/insights/insights.ts buildInsights 同一组规则、顺序与文案（改动需两端同步） ──
  function buildInsights(data) {
    const monitoring = data.monitoring || {};
    const metrics = data.metrics || {};
    const runtime = monitoring.runtime || {};
    const items = [];
    const push = (tone, title, detail, page) => items.push({ tone, title, detail, page });

    if (runtime.database_degraded === true) {
      push("danger", t("insights.databaseDegraded", "数据库处于降级状态"),
        runtime.database_start_error ? String(runtime.database_start_error) : t("insights.databaseNotReady", "数据库服务未完整启动。"), "monitoring");
    }
    const backlog = reviewBacklog(data).total;
    if (backlog > 0) {
      push(backlog > 20 ? "danger" : "warning", t("insights.reviewBacklog", "审查队列存在积压"),
        t("insights.reviewBacklogDetail", "当前约 {count} 条记录等待处理。").replace("{count}", fmt(backlog, 0)), "reviews");
    }
    const filteredRaw = metrics.filtered_messages ?? (metrics.messages || {}).filtered;
    const filtered = filteredRaw === undefined || filteredRaw === null ? 0 : safeNum(filteredRaw);
    if (filtered > 0) {
      push("default", t("insights.filtered", "过滤链路持续工作"),
        t("insights.filteredDetail", "{count} 条消息因质量或规则未进入学习。").replace("{count}", fmt(filtered, 0)), "monitoring");
    }
    const checks = (monitoring.health || {}).checks;
    const failures = Object.values(isRecord(checks) ? checks : {})
      .filter((item) => isRecord(item) && item.status && item.status !== "healthy").length;
    if (failures > 0) {
      push("danger", t("insights.healthFailed", "健康检查发现异常"),
        t("insights.healthFailedDetail", "{count} 项检查未处于健康状态。").replace("{count}", fmt(failures, 0)), "monitoring");
    }
    const { score } = intelligenceScore(data);
    if (score > 0 && score < 60) {
      push("warning", t("insights.lowScore", "智能评分偏低"),
        t("insights.lowScoreDetail", "综合评分 {score}，建议查看表达样本和学习批次。").replace("{score}", fmt(score)), "monitoring");
    }
    const delegation = (data.integrations || {}).delegation || {};
    if (delegation.memory_delegated || delegation.reply_delegated) {
      push("default", t("insights.delegationEnabled", "伴随插件委托已启用"), t("insights.delegationDetail", "记忆委托: {memory}，回复委托: {reply}。")
        .replace("{memory}", delegation.memory_delegated ? t("state.yes", "是") : t("state.no", "否"))
        .replace("{reply}", delegation.reply_delegated ? t("state.yes", "是") : t("state.no", "否")), "integrations");
    }
    Object.entries(data.errors || {}).forEach(([key, value]) => {
      push("warning", t("insights.moduleFailed", "模块 {name} 读取失败").replace("{name}", key), String(value), "monitoring");
    });
    if (!items.length) {
      push("success", t("insights.noIssues", "暂未发现需要立即处理的问题"), t("insights.noIssuesDetail", "当前快照没有明显积压或健康告警。"), "overview");
    }
    return items;
  }

  function insightLevel(tone) {
    return tone === "danger" ? t("insights.levelHigh", "高") : tone === "warning" ? t("insights.levelMedium", "中") : t("insights.levelInfo", "提示");
  }

  function renderInsights(data) {
    const insights = buildInsights(data || state.dashboard || {});
    setHtml("ai-insight-list", insights.map((item) => `
      <button class="insight-card tone-${escapeAttr(item.tone)}" type="button" data-route-card="${escapeAttr(item.page)}">
        <span class="insight-card-head">${pill(insightLevel(item.tone), toneClass(item.tone))}<strong>${escapeHtml(item.title)}</strong></span>
        <span class="insight-card-detail">${escapeHtml(item.detail)}</span>
        <span class="card-arrow" aria-hidden="true">→</span>
      </button>
    `).join("") || empty());
  }

  // 「复制摘要」：与独立版一致，每条巡检一行「- 标题: 说明」
  function insightSummaryText(data) {
    return buildInsights(data || {}).map((item) => `- ${item.title}: ${item.detail}`).join("\n");
  }

  // ── 运行监控（对齐独立版 MonitoringPage：4 读数 + 系统健康 / 监控热点 + 模型调用） ──
  function renderMonitoring(data) {
    const monitoring = data.monitoring || {};
    const health = monitoring.health || {};
    const functions = monitoring.functions || {};
    const metrics = data.metrics || {};
    const healthSource = health.checks ?? health.items ?? health;
    const healthRows = Array.isArray(healthSource)
      ? healthSource
      : Object.entries(isRecord(healthSource) ? healthSource : {}).map(([name, value]) => ({ name, ...(isRecord(value) ? value : {}) }));
    const functionRows = Array.isArray(functions.functions) ? functions.functions : [];
    const { score, dimensions } = intelligenceScore(data);

    setText("mon-stat-checks", fmt(healthRows.length, 0));
    setText("mon-stat-functions", fmt(functionRows.length, 0));
    setText("mon-stat-trace", functions.trace_enabled ? t("monitoring.traceEnabled", "已启用") : t("monitoring.traceDisabled", "未启用"));
    setText("mon-stat-overall", textOrDash(health.overall ?? health.status));
    setText("mon-stat-score", fmt(score));
    setText("mon-stat-score-note", dimensions
      ? t("monitoring.scoreNote", "已有 {count} 个维度参与评估。").replace("{count}", fmt(dimensions, 0))
      : t("monitoring.scoreEmpty", "智能指标服务暂未产生维度数据。"));

    setHtml("health-list", healthRows.map((item) => {
      const tone = item.status === "healthy" || item.ok === true ? "success" : item.status === "unhealthy" ? "danger" : "warning";
      return `<div class="check-row">
        <div><strong>${escapeHtml(textOrDash(item.name ?? item.key))}</strong><small>${escapeHtml(detailText(item.detail ?? item.message))}</small></div>
        ${pill(textOrDash(item.status ?? (item.ok ? "healthy" : "unknown")), toneClass(tone))}
      </div>`;
    }).join("") || empty(t("empty.healthChecks", "暂无健康检查数据")));

    // 监控热点：与独立版 ProgressBar 同语义（avg_ms ?? total_ms ?? calls，封顶 100，显示 N%）
    setHtml("function-list", functionRows.map((item) => {
      const value = Math.max(0, Math.min(100, Number(item.avg_ms ?? item.total_ms ?? item.calls) || 0));
      return `<div class="bar-row stacked">
        <span>${escapeHtml(textOrDash(item.name ?? item.function))}</span>
        <strong>${escapeHtml(value.toFixed(0))}%</strong>
        <div class="bar-track"><div class="bar-fill" style="--value:${value}"></div></div>
      </div>`;
    }).join("") || empty(t("monitoring.noTrace", "当前没有函数追踪样本；可在配置中开启 trace。")));

    const llmSource = metrics.llm_call_breakdown ?? metrics.llm_calls ?? metrics.filter_model_summary ?? {};
    const llmRows = Array.isArray(llmSource)
      ? llmSource
      : Object.entries(isRecord(llmSource) ? llmSource : {}).map(([provider, calls]) =>
        (typeof calls === "object" ? { provider, ...(isRecord(calls) ? calls : {}) } : { provider, calls }));
    setText("llm-total-calls", `${fmt(safeNum((metrics.llm_call_summary || {}).total_calls), 0)} ${t("units.calls", "次调用")}`);
    setHtml("llm-call-list", llmRows.map((item) => `<div class="check-row">
        <div>
          <strong>${escapeHtml(textOrDash(item.provider_label ?? item.provider_type ?? item.provider ?? item.name ?? item.model))}</strong>
          <small>${escapeHtml(t("monitoring.llmMeta", "平均 {avg}ms · 失败 {errors}")
            .replace("{avg}", fmt(safeNum(item.avg_response_time_ms), 0))
            .replace("{errors}", fmt(safeNum(item.error_count ?? item.errors), 0)))}</small>
        </div>
        ${pill(fmt(safeNum(item.total_calls ?? item.calls ?? item.count), 0), item.is_abnormal === true || item.abnormal === true ? "danger" : "")}
      </div>`).join("") || empty(t("empty.llmCalls", "暂无模型调用统计")));
  }

  // ── 双端对齐共用工具：与独立版 lib/format.ts、lib/diff.ts、lib/review.ts 同口径 ──
  function formatTime(value) {
    if (value === null || value === undefined || value === "") return "--";
    const raw = typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value;
    const date = typeof raw === "number" ? new Date(raw > 1e12 ? raw : raw * 1000) : new Date(String(raw));
    if (Number.isNaN(date.getTime())) return String(value);
    try {
      return date.toLocaleString(locale());
    } catch (_) {
      return date.toLocaleString();
    }
  }

  function summarize(value) {
    if (value === null || value === undefined || value === "") return "--";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch (_) {
      return String(value);
    }
  }

  // 模板占位符替换：用函数替换避免用户内容中的 `$&` 等被 String.replace 解释
  function fill(template, values) {
    return String(template).replace(/\{(\w+)\}/g, (match, key) => (
      Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
    ));
  }

  function emptyDetail(title, detail) {
    return `<div class="empty-state with-detail"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></div>`;
  }

  // 读数卡（值为已格式化文本；与独立版 StatCard 同构）
  function readoutCards(items) {
    return items.map(([label, value]) => `<article class="stat-card small">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>`).join("");
  }

  // 与独立版一致：成功提示固定文案，失败优先展示后端原因
  function operationToast(result, okText, failText) {
    const ok = !!(result && result.success);
    showToast(ok ? okText : ((result && result.message) || failText), ok ? "ok" : "error");
    return ok;
  }

  // 写操作后静默刷新首页 / AI 巡检共享快照（对齐独立版 dashboard.refresh(true)）
  function syncDashboardSnapshot() {
    loadDashboard(true, { quiet: true }).catch(() => {});
  }

  // 分页（与独立版 Pagination 同构：上一页 / 第 N / M 页 / 下一页）
  function paginationHtml(target, page, totalPages) {
    const total = Math.max(1, totalPages);
    return `${button(t("pagination.prev", "上一页"), `data-page-nav="${escapeAttr(target)}" data-page-to="${page - 1}" ${page <= 1 ? "disabled" : ""}`)}
      <span>${escapeHtml(fill(t("pagination.status", "第 {page} / {total} 页"), { page, total }))}</span>
      ${button(t("pagination.next", "下一页"), `data-page-nav="${escapeAttr(target)}" data-page-to="${page + 1}" ${page >= totalPages ? "disabled" : ""}`)}`;
  }

  // 下载 JSON 文件（插件页 iframe 带 allow-downloads，与独立版导出行为一致）
  function downloadJson(filename, data) {
    const text = JSON.stringify(data, null, 2);
    const canObjectUrl = typeof Blob !== "undefined" && typeof URL !== "undefined" && typeof URL.createObjectURL === "function";
    const href = canObjectUrl
      ? URL.createObjectURL(new Blob([text], { type: "application/json" }))
      : `data:application/json;charset=utf-8,${encodeURIComponent(text)}`;
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    if (canObjectUrl) setTimeout(() => URL.revokeObjectURL(href), 0);
  }

  function buildLineDiff(beforeValue, afterValue) {
    const before = String(beforeValue ?? "").split(/\r?\n/);
    const after = String(afterValue ?? "").split(/\r?\n/);
    const table = Array.from({ length: before.length + 1 }, () => new Array(after.length + 1).fill(0));
    for (let i = before.length - 1; i >= 0; i -= 1) {
      for (let j = after.length - 1; j >= 0; j -= 1) {
        table[i][j] = before[i] === after[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }
    const result = [];
    let i = 0;
    let j = 0;
    while (i < before.length || j < after.length) {
      if (i < before.length && j < after.length && before[i] === after[j]) {
        result.push({ kind: "same", text: before[i] }); i += 1; j += 1;
      } else if (j < after.length && (i >= before.length || table[i][j + 1] >= table[i + 1][j])) {
        result.push({ kind: "add", text: after[j] }); j += 1;
      } else {
        result.push({ kind: "remove", text: before[i] }); i += 1;
      }
    }
    return result;
  }

  function asText(value) {
    if (value === undefined || value === null) return "";
    return typeof value === "string" ? value : String(value);
  }

  // 后端把 before/after 人格快照放在 change_preview（待审）或 change_snapshot（已审）里（issue #280）
  function reviewChangePreview(item) {
    const value = item.change_preview ?? item.persona_change_preview ?? item.change_snapshot ?? item.persona_change_snapshot;
    return isRecord(value) ? value : {};
  }

  function reviewBeforePrompt(item) {
    const preview = reviewChangePreview(item);
    return asText(preview.before_system_prompt ?? item.before_system_prompt ?? item.before ?? item.original_content ?? item.original_prompt);
  }

  function reviewAfterPrompt(item) {
    const preview = reviewChangePreview(item);
    return asText(preview.after_system_prompt ?? item.after_system_prompt ?? item.after ?? item.new_content
      ?? item.proposed_content ?? preview.proposed_content ?? item.content);
  }

  function reviewBeginDialogs(item) {
    const preview = reviewChangePreview(item);
    const asList = (value) => (Array.isArray(value) ? value : []);
    return {
      before: asList(preview.before_begin_dialogs ?? item.before_begin_dialogs),
      after: asList(preview.after_begin_dialogs ?? item.after_begin_dialogs),
    };
  }

  function formatDialogLines(dialogs) {
    return dialogs
      .map((dialog) => (typeof dialog === "string" ? dialog : JSON.stringify(dialog)))
      .filter((line) => line.length > 0)
      .join("\n");
  }

  function reviewChangeMeta(item) {
    const preview = reviewChangePreview(item);
    const meta = [];
    const mode = asText(preview.application_mode);
    if (mode) meta.push(fill(t("reviews.card.metaMode", "应用方式：{value}"), { value: mode }));
    const fieldSource = preview.target_fields ?? preview.affected_fields;
    const fields = (Array.isArray(fieldSource) ? fieldSource : []).map(asText).filter(Boolean);
    if (fields.length) meta.push(fill(t("reviews.card.metaFields", "影响字段：{value}"), { value: fields.join("、") }));
    const groupId = asText(preview.group_id ?? item.group_id);
    if (groupId) meta.push(fill(t("reviews.card.metaGroup", "群组：{value}"), { value: groupId }));
    const proposed = asText(preview.proposed_content);
    if (proposed) meta.push(fill(t("reviews.card.metaProposed", "建议内容：{count} 字"), { count: proposed.length }));
    return meta;
  }

  function reviewHasChange(item) {
    if (reviewBeforePrompt(item) || reviewAfterPrompt(item)) return true;
    const dialogs = reviewBeginDialogs(item);
    return dialogs.before.length > 0 || dialogs.after.length > 0;
  }

  function reviewTitle(item) {
    return textOrDash(item.title ?? item.content ?? item.jargon ?? item.pattern ?? item.update_type ?? item.description ?? `#${item.id}`);
  }

  function diffLinesHtml(lines) {
    return `<div class="diff-lines">${lines.map((line) => `<div class="diff-line ${line.kind}"><span>${line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</span>${escapeHtml(line.text || " ")}</div>`).join("")}</div>`;
  }

  // 审查卡（与独立版 components/business/ReviewCard 同字段、同分区、同动作）
  function reviewCardHtml(item, kind, options = {}) {
    const id = normalizeId(item.id);
    const before = reviewBeforePrompt(item);
    const after = reviewAfterPrompt(item);
    const dialogs = reviewBeginDialogs(item);
    const meta = reviewChangeMeta(item);
    const proposedRaw = reviewChangePreview(item).proposed_content ?? item.proposed_content;
    const proposed = typeof proposedRaw === "string" ? proposedRaw : "";
    const showChanges = kind !== "jargon" && (reviewHasChange(item) || meta.length > 0 || proposed);
    const actionAttrs = (action) => `data-review-action="${action}" data-kind="${escapeAttr(kind)}" data-id="${escapeAttr(id)}"`;
    const status = item.status ?? "pending";
    const tone = item.status === "approved" ? "ok" : item.status === "rejected" ? "danger" : "warn";
    const changes = showChanges ? `<details class="review-diff">
          <summary>${escapeHtml(t("reviews.card.viewChanges", "查看变更详情"))}</summary>
          ${before || after ? diffLinesHtml(buildLineDiff(before, after)) : ""}
          ${dialogs.before.length || dialogs.after.length
    ? `<h4 class="review-section-title">${escapeHtml(t("reviews.card.dialogChanges", "示例对话变化"))}</h4>${diffLinesHtml(buildLineDiff(formatDialogLines(dialogs.before), formatDialogLines(dialogs.after)))}`
    : ""}
          ${meta.length ? `<p class="review-meta">${escapeHtml(meta.join(" · "))}</p>` : ""}
          ${proposed ? `<details class="review-proposal"><summary>${escapeHtml(fill(t("reviews.card.proposal", "建议内容原文（{count} 字）"), { count: proposed.length }))}</summary><pre>${escapeHtml(proposed)}</pre></details>` : ""}
        </details>` : "";
    return `<article class="review-item review-card${options.selectable ? " selectable" : ""}">
      ${options.selectable ? reviewCheckbox(kind, id) : ""}
      <div class="review-card-body">
        <div class="review-card-head">
          <div><strong>${escapeHtml(reviewTitle(item))}</strong><small>${escapeHtml(formatTime(item.created_at))}</small></div>
          ${pill(textOrDash(status), tone)}
        </div>
        ${item.definition || item.meaning || item.review_detail ? `<p>${escapeHtml(textOrDash(item.definition ?? item.meaning ?? item.review_detail))}</p>` : ""}
        ${changes}
        ${item.pattern_details || item.few_shot_pairs ? `<details class="review-structured"><summary>${escapeHtml(t("reviews.card.structured", "结构化信息"))}</summary><pre>${escapeHtml(summarize(item.pattern_details ?? item.few_shot_pairs))}</pre></details>` : ""}
        <details class="review-raw"><summary>${escapeHtml(t("reviews.card.raw", "查看原始审查数据"))}</summary><pre>${escapeHtml(summarize(item))}</pre></details>
        <div class="review-actions">
          ${button(t("actions.pass", "通过"), actionAttrs("approve"), "ghost-button success-button")}
          ${button(t("actions.rejectBack", "驳回"), actionAttrs("reject"), "ghost-button warning-button")}
          ${kind === "style" && options.editable ? button(t("actions.edit", "编辑"), `data-style-action="edit" data-id="${escapeAttr(id)}"`) : ""}
          ${button(t("actions.delete", "删除"), actionAttrs("delete"), "danger-button")}
        </div>
      </div>
    </article>`;
  }

  function reviewQueueTitle(kind) {
    if (kind === "persona") return t("reviews.queue.persona", "待审人格");
    if (kind === "style") return t("reviews.queue.style", "风格审查");
    return t("reviews.queue.jargon", "黑话审查");
  }

  // ── 审查队列（对齐独立版 ReviewsPage：三栏队列 + 最近学习批次） ──
  async function loadReviews(force) {
    const params = reviewSearchParams();
    const [data] = await Promise.all([
      cached(`reviews:${JSON.stringify(params)}`, () => apiGet("reviews", params), force),
      loadReviewBatches(force).catch((error) => showToast(error.message || t("reviews.batches.failed", "批次操作失败"), "error")),
    ]);
    state.reviewParams = params;
    renderReviews(data);
  }

  function renderReviews(data) {
    state.pageData.reviews = data;
    ["persona", "style", "jargon"].forEach((kind) => {
      const items = reviewQueueItems(kind, data);
      pruneSelection(selectedReviewSet(kind), items.map((item) => item.id));
      setHtml(`${kind}-review-list`, items.map((item) => reviewCardHtml(item, kind, { selectable: true, editable: true })).join("")
        || empty(t("reviews.queueEmpty", "队列为空")));
    });
    refreshSelectionLabels();
    showErrors(data.errors || {});
  }

  async function loadReviewBatches(force) {
    const params = { page: state.reviewBatchPage, page_size: 10 };
    const data = await cached(`batches:${JSON.stringify(params)}`, () => apiGet("batches", params), force);
    renderReviewBatches(data);
  }

  function renderReviewBatches(data) {
    state.pageData.reviewBatches = data;
    const rows = listOf(data.batches ?? data).filter(isRecord);
    state.reviewBatchPages = Math.max(1, Number(data.total_pages ?? 1) || 1);
    setHtml("review-batch-list", rows.map((item) => {
      const batchId = normalizeId(item.id ?? item.batch_id);
      const score = safeNum(item.quality_score);
      const quality = item.quality_score === undefined
        ? "--"
        : fill(t("reviews.batches.quality", "quality {value}"), { value: score.toFixed(score < 1 ? 3 : 1) });
      return `<article class="batch-card">
        <div class="batch-card-head"><strong>${escapeHtml(textOrDash(item.batch_name ?? item.batch_id ?? t("reviews.batches.defaultName", "学习批次")))}</strong><span>${escapeHtml(quality)}</span></div>
        <p>${escapeHtml(fill(t("reviews.batches.meta", "群组 {group} · 开始 {start} · 结束 {end}"), {
    group: textOrDash(item.group_id),
    start: formatTime(item.start_time),
    end: formatTime(item.end_time),
  }))}</p>
        <div class="inline-actions">
          ${item.group_id ? button(t("reviews.batches.relearn", "重跑学习"), `data-batch-record-action="relearn" data-group-id="${escapeAttr(item.group_id)}"`) : ""}
          ${batchId ? button(t("reviews.batches.delete", "删除批次"), `data-batch-record-action="delete" data-id="${escapeAttr(batchId)}"`, "danger-button") : ""}
        </div>
      </article>`;
    }).join("") || empty(t("reviews.batches.empty", "暂无批次记录")));
    setHtml("review-batch-pagination", paginationHtml("batches", state.reviewBatchPage, state.reviewBatchPages));
  }

  // ── 黑话学习（对齐独立版 JargonLearningPage：黑话词库 + 导入面板；读数 / 范围 / 批量为双端并集） ──
  function jargonListParams() {
    const confirmed = $("jargon-confirmed")?.value || "";
    const filter = $("jargon-filter")?.value || "";
    const keyword = ($("jargon-keyword")?.value || "").trim();
    const params = { page: state.jargon.page, page_size: 10 };
    if (keyword) params.keyword = keyword;
    if (confirmed === "pending") params.pending = "true";
    else if (confirmed) params.confirmed = confirmed;
    if (filter) params.filter = filter;
    return params;
  }

  async function loadJargon(force) {
    const params = jargonListParams();
    let data;
    try {
      data = await cached(`jargon:${JSON.stringify(params)}`, () => apiGet("jargon", params), force);
    } catch (error) {
      showToast(error.message || t("jargon.loadFailed", "黑话加载失败"), "error");
      return;
    }
    renderJargon(data);
  }

  // is_complete 只表示审查/推断结束；is_jargon === false 才是明确驳回（issue #274）
  function jargonStatusBadge(item) {
    if (item.is_confirmed) return pill(t("jargon.confirmed", "已确认"), "ok");
    if (!item.is_complete) return pill(textOrDash(item.status ?? t("jargon.pendingReview", "待审")), "warn");
    return item.is_jargon === false
      ? pill(t("jargon.rejected", "已驳回"), "danger")
      : pill(t("jargon.completed", "已完成"));
  }

  function renderJargonImportGroups(groups) {
    const select = $("jargon-import-group");
    if (!select) return;
    const current = select.value;
    const options = [`<option value="__global__">${escapeHtml(t("jargon.import.globalScope", "全局共享（所有群生效）"))}</option>`]
      .concat((groups || []).map((group) => {
        const id = String(group.group_id ?? group.id ?? "");
        if (!id) return "";
        const name = String(group.group_name ?? group.group_id ?? t("jargon.import.unknownGroup", "未知群组"));
        const count = Number(group.count ?? group.confirmed_jargon ?? 0) || 0;
        return `<option value="${escapeAttr(id)}">${escapeHtml(fill(t("jargon.import.groupOption", "{name}（{count} 条）"), { name, count }))}</option>`;
      }));
    select.innerHTML = options.join("");
    if (current && qsa("option", select).some((option) => option.value === current)) select.value = current;
  }

  function renderJargonImportReport(result) {
    const output = $("jargon-import-output");
    if (!output) return;
    if (!result) {
      output.hidden = true;
      output.innerHTML = "";
      return;
    }
    const detail = result.result || {};
    const failed = ((detail.details || {}).failed) || [];
    output.hidden = false;
    output.innerHTML = `<strong>${escapeHtml(result.message || detail.message || "")}</strong>${failed.length
      ? `<ul>${failed.map((failure) => `<li>${escapeHtml(fill(t("jargon.import.failedLine", "第 {line} 行「{term}」：{reason}"), {
        line: failure.line,
        term: failure.term || "",
        reason: failure.reason || "",
      }))}</li>`).join("")}</ul>`
      : ""}`;
  }

  function syncJargonImportButton() {
    const submit = $("jargon-import-submit");
    if (submit && !submit.classList.contains("is-busy")) {
      submit.disabled = !($("jargon-import-text")?.value || "").trim();
    }
  }

  function jargonRowHtml(item) {
    const id = normalizeId(item.id);
    if (state.jargon.editingId === id) {
      const draft = state.jargon.draft || { content: "", meaning: "" };
      return `<article class="data-row jargon-row editing">
        <div class="jargon-edit-grid">
          <label class="stack-field"><span>${escapeHtml(t("jargon.term", "词条"))}</span><input id="jargon-edit-content" data-jargon-draft="content" value="${escapeAttr(draft.content)}"></label>
          <label class="stack-field"><span>${escapeHtml(t("jargon.definition", "释义"))}</span><textarea id="jargon-edit-meaning" data-jargon-draft="meaning" rows="3">${escapeHtml(draft.meaning)}</textarea></label>
          <div class="inline-actions">
            ${button(t("actions.save", "保存"), `data-jargon-action="save" data-id="${escapeAttr(id)}"`, "ghost-button success-button")}
            ${button(t("actions.cancel", "取消"), `data-jargon-action="cancel" data-id="${escapeAttr(id)}"`)}
          </div>
        </div>
      </article>`;
    }
    return `<article class="data-row jargon-row">
      <div class="jargon-row-main">
        ${jargonCheckbox(id)}
        <div class="jargon-row-copy">
          <strong>${escapeHtml(textOrDash(item.content ?? item.jargon))}</strong>
          <p>${escapeHtml(textOrDash(item.meaning ?? item.definition))}</p>
          <small>${escapeHtml(formatTime(item.created_at))}</small>
        </div>
        <span class="jargon-row-group">${escapeHtml(textOrDash(item.group_id))}</span>
        ${jargonStatusBadge(item)}
        ${pill(item.is_global ? t("jargon.global", "全局") : t("jargon.local", "本地"))}
      </div>
      <div class="inline-actions">
        ${item.is_confirmed ? "" : button(t("actions.confirm", "确认"), `data-jargon-action="approve" data-id="${escapeAttr(id)}"`, "ghost-button success-button")}
        ${item.is_confirmed ? "" : button(t("actions.rejectBack", "驳回"), `data-jargon-action="reject" data-id="${escapeAttr(id)}"`, "ghost-button warning-button")}
        ${button(t("actions.edit", "编辑"), `data-jargon-action="edit" data-id="${escapeAttr(id)}"`)}
        ${button(item.is_global ? t("actions.unsetGlobal", "取消全局") : t("actions.setGlobal", "设为全局"), `data-jargon-action="toggle_global" data-id="${escapeAttr(id)}"`)}
        ${button(t("actions.delete", "删除"), `data-jargon-action="delete" data-id="${escapeAttr(id)}"`, "danger-button")}
      </div>
    </article>`;
  }

  function renderJargon(data) {
    state.pageData.currentJargonData = data;
    const stats = data.stats || {};
    setHtml("jargon-stat-grid", readoutCards([
      [t("jargon.stats.candidates", "候选词"), fmt(stats.total_candidates, 0)],
      [t("jargon.stats.confirmed", "已确认"), fmt(stats.confirmed_jargon, 0)],
      [t("jargon.stats.inferred", "推断完成"), fmt(stats.completed_inference, 0)],
      [t("jargon.stats.activeGroups", "活跃群组"), fmt(stats.active_groups, 0)],
    ]));
    const listing = data.list || {};
    const items = listOf(listing).filter(isRecord);
    state.jargon.items = items;
    // 关键词检索返回全部匹配（单页）；普通列表按后端分页（每页 10 条）
    state.jargon.totalPages = Math.max(1, Number(listing.total_pages ?? Math.ceil(Number(listing.total ?? items.length) / 10)) || 1);
    pruneSelection(state.selectedJargon, items.map((item) => item.id));
    setHtml("jargon-list", items.map((item) => jargonRowHtml(item)).join("") || empty(t("jargon.empty", "没有匹配的黑话词条")));
    setHtml("jargon-pagination", paginationHtml("jargon", state.jargon.page, state.jargon.totalPages));
    renderJargonImportGroups(data.groups || []);
    refreshSelectionLabels();
    showErrors(data.errors || {});
  }

  async function reloadJargon() {
    clearCached("jargon");
    await loadJargon(true);
  }

  async function submitJargonImport(buttonEl) {
    const importText = $("jargon-import-text")?.value || "";
    if (!importText.trim()) {
      showToast(t("jargon.import.empty", "请先填写要导入的词条"), "warn");
      return;
    }
    const scopeValue = $("jargon-import-group")?.value || "__global__";
    const groupId = scopeValue === "__global__" ? "" : scopeValue;
    buttonEl.disabled = true;
    buttonEl.classList.add("is-busy");
    renderJargonImportReport(null);
    try {
      const result = await apiPost("jargon/action", {
        action: "import_jargons",
        text: importText,
        group_id: groupId,
        is_global: !groupId,
      });
      // 与独立版一致：服务受理即按成功提示，部分行失败在导入报告中逐行列出；输入框内容保留
      const ok = result.success !== false || (result.result || {}).success === true;
      showToast(result.message || (ok ? t("jargon.import.done", "导入完成") : t("jargon.import.failed", "导入失败")), ok ? "ok" : "error");
      if (ok) {
        renderJargonImportReport(result);
        state.jargon.page = 1;
        await reloadJargon();
        syncDashboardSnapshot();
      }
    } catch (error) {
      showToast(error.message || t("jargon.import.failed", "导入失败"), "error");
    } finally {
      buttonEl.classList.remove("is-busy");
      syncJargonImportButton();
    }
  }

  // ── 表达方式学习（双端并集：读数卡 + 表达样本库四分类 + 构成 + 学习模式三栏） ──
  const CONTENT_BUCKETS = ["dialogues", "analysis", "features", "history"];
  const CONTENT_BUCKET_FALLBACK = { dialogues: "对话", analysis: "分析", features: "特征", history: "历史" };
  const contentBucketLabel = (bucket) => t(`content.tabs.${bucket}`, CONTENT_BUCKET_FALLBACK[bucket] || bucket);

  async function loadStyle(force) {
    const data = await cached("style", () => apiGet("style"), force);
    renderStyle(data);
  }

  function renderStyle(data) {
    state.pageData.style = data;
    const stats = ((data.results || {}).statistics) || {};
    setHtml("style-stat-grid", readoutCards([
      [t("style.stats.samples", "风格样本"), fmt(stats.unique_styles || stats.total_samples, 0)],
      [t("style.stats.avgConfidence", "平均置信度"), fmt(stats.avg_confidence, 1)],
      [t("style.stats.totalSamples", "总样本"), fmt(stats.total_samples, 0)],
      [t("style.stats.latestUpdate", "最近更新"), stats.latest_update ? formatTime(stats.latest_update) : "--"],
    ]));
    const content = data.content || {};
    const accents = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];
    renderGenericBarChart("style-composition-chart", CONTENT_BUCKETS.map((bucket, index) => ({
      title: contentBucketLabel(bucket),
      metric: listOf(content[bucket]).length,
      accent: accents[index],
    })));
    renderStyleSamples();
    const patterns = data.patterns || {};
    const groups = [
      [t("style.patterns.emotion", "情绪模式"), patterns.emotion_patterns],
      [t("style.patterns.language", "语言模式"), patterns.language_patterns],
      [t("style.patterns.topic", "话题模式"), patterns.topic_patterns],
    ];
    setHtml("style-pattern-columns", groups.map(([title, list]) => {
      const rows = Array.isArray(list) ? list : [];
      return `<div class="pattern-column">
        <h4><span>${escapeHtml(title)}</span>${pill(fmt(rows.length, 0))}</h4>
        ${rows.slice(0, 12).map((item) => `<span class="pattern-chip">${escapeHtml((item && (item.name || item.pattern || item.text)) || "")}</span>`).join("") || empty(t("empty.patterns", "暂无模式"))}
      </div>`;
    }).join(""));
  }

  function renderStyleSamples() {
    const content = ((state.pageData.style || {}).content) || {};
    qsa("#style-sample-tabs button").forEach((btn) => btn.classList.toggle("active", btn.dataset.styleBucket === state.styleBucket));
    const items = listOf(content[state.styleBucket]).filter(isRecord).slice(0, 20);
    setHtml("style-sample-list", items.map((item) => `<details class="sample-item">
        <summary>${escapeHtml(textOrDash(item.title ?? item.name ?? item.id ?? t("content.itemFallback", "内容项")))}</summary>
        <pre class="code-preview">${escapeHtml(summarize(item))}</pre>
      </details>`).join("") || empty());
  }

  // ── 人格学习（对齐独立版 PersonaLearningPage：当前人格 / 人格备份 / 人格列表 / 最近已审查 / 待审人格更新） ──
  async function loadPersona(force) {
    const data = await cached("persona", () => apiGet("persona", { group_id: "default", limit: 8 }), force);
    renderPersona(data);
  }

  function personaIdOf(item) {
    return String(item.persona_id ?? item.id ?? item.name ?? "");
  }

  function personaNameOf(item) {
    return textOrDash(item.name ?? item.persona_id ?? item.id ?? t("persona.unnamed", "未命名人格"));
  }

  function personaPromptOf(item) {
    return String(item.system_prompt ?? item.prompt ?? "");
  }

  function reviewedStatusText(item) {
    if (item.status === "approved") return t("persona.statusApproved", "已通过");
    if (item.status === "rejected") return t("persona.statusRejected", "已驳回");
    return textOrDash(item.status);
  }

  function renderPersonaCurrent(current) {
    const snapshot = isRecord(current) ? current : {};
    if (!Object.keys(snapshot).length) {
      setHtml("persona-current", empty(t("persona.emptySnapshot", "暂无人格快照")));
      return;
    }
    const persona = isRecord(snapshot.persona) ? snapshot.persona : {};
    setHtml("persona-current", `<div class="persona-current">
      <div class="persona-current-head">
        <h4>${escapeHtml(textOrDash(persona.name ?? persona.persona_id ?? t("persona.defaultName", "Default Persona")))}</h4>
        ${pill(snapshot.degraded ? t("persona.degraded", "降级预览") : t("persona.active", "当前生效"), snapshot.degraded ? "warn" : "ok")}
      </div>
      <section class="stat-grid compact">${readoutCards([
    [t("persona.stats.promptLength", "提示词字数"), fmt(snapshot.prompt_length, 0)],
    [t("persona.stats.beginDialogs", "开场对话"), fmt(snapshot.begin_dialog_count, 0)],
    [t("persona.stats.toolCount", "工具数量"), fmt(snapshot.tool_count, 0)],
    [t("persona.stats.currentGroup", "当前群组"), textOrDash(snapshot.group_id || "default")],
  ])}</section>
      <p class="persona-current-prompt">${escapeHtml(textOrDash(snapshot.prompt_preview ?? persona.prompt ?? persona.system_prompt))}</p>
      <details><summary>${escapeHtml(t("persona.fullState", "查看完整状态"))}</summary><pre class="code-preview">${escapeHtml(summarize(snapshot))}</pre></details>
    </div>`);
  }

  function renderPersona(data) {
    state.pageData.persona = data;
    renderPersonaCurrent(data.current);

    const backups = listOf(data.backups).filter(isRecord);
    setText("persona-backup-count", fmt(backups.length, 0));
    setHtml("persona-backup-list", backups.map((item) => {
      const attrs = `data-id="${escapeAttr(item.id ?? item.backup_id ?? item.name ?? "")}" data-group-id="${escapeAttr(item.group_id ?? "")}"`;
      return `<div class="table-row backup-row">
        <div><strong>${escapeHtml(textOrDash(item.backup_name ?? item.name ?? item.id))}</strong><small>${escapeHtml(formatTime(item.created_at ?? item.timestamp))}</small></div>
        <div class="row-actions">
          ${button(t("persona.viewBackup", "查看备份"), `data-persona-action="backup_detail" ${attrs}`)}
          ${button(t("actions.restore", "恢复"), `data-persona-action="backup_restore" ${attrs}`, "ghost-button warning-button")}
          ${button(t("actions.delete", "删除"), `data-persona-action="backup_delete" ${attrs}`, "danger-button")}
        </div>
      </div>`;
    }).join("") || empty(t("persona.emptyBackups", "暂无备份")));

    const personas = Array.isArray(data.personas) ? data.personas.filter(isRecord) : [];
    state.pageData.lastPersonaItems = personas;
    setHtml("persona-list", personas.map((item) => {
      const id = personaIdOf(item);
      const attrs = `data-persona-id="${escapeAttr(id)}"`;
      return `<div class="table-row persona-row">
        <div>
          <strong>${escapeHtml(personaNameOf(item))}</strong>
          <small>${escapeHtml(fill(t("persona.listMeta", "{id} · 提示词 {length} 字 · 示例对话 {count} 条"), {
    id: textOrDash(id),
    length: personaPromptOf(item).length,
    count: listOf(item.begin_dialogs).length,
  }))}</small>
        </div>
        <div class="row-actions">
          ${button(t("persona.view", "查看人格"), `data-persona-action="view" ${attrs}`)}
          ${button(t("persona.edit", "编辑人格"), `data-persona-action="edit" ${attrs}`)}
          ${button(t("persona.export", "导出人格"), `data-persona-action="export" ${attrs}`)}
          ${button(t("persona.delete", "删除人格"), `data-persona-action="delete" ${attrs}`, "danger-button")}
        </div>
      </div>`;
    }).join("") || emptyDetail(t("empty.personaList", "暂无人格列表"), t("persona.emptyListDetail", "AstrBot PersonaManager 未提供人格数据。")));

    const reviewed = listOf(data.reviewed).filter(isRecord).slice(0, 8);
    state.pageData.lastReviewedItems = reviewed;
    setText("persona-reviewed-count", fmt(reviewed.length, 0));
    setHtml("persona-reviewed-list", reviewed.map((item) => {
      const tone = item.status === "approved" ? "ok" : item.status === "rejected" ? "danger" : "";
      const id = normalizeId(item.id);
      return `<div class="table-row reviewed-row">
        <div class="reviewed-head">
          <div>
            <strong>${escapeHtml(textOrDash(item.update_type ?? item.title ?? item.review_source ?? `#${item.id}`))}</strong>
            <small>${escapeHtml(formatTime(item.review_time))} · ${escapeHtml(textOrDash(item.review_source ?? item.group_id))}</small>
          </div>
          ${pill(reviewedStatusText(item), tone)}
        </div>
        <p>${escapeHtml(textOrDash(String(item.proposed_content ?? item.new_content ?? item.reason ?? "").slice(0, 120)))}</p>
        <div class="row-actions">
          ${button(t("persona.viewDetails", "查看详情"), `data-persona-action="reviewed_detail" data-id="${escapeAttr(id)}"`)}
          ${button(t("persona.revert", "撤回"), `data-persona-action="revert" data-id="${escapeAttr(id)}"`, "ghost-button warning-button")}
        </div>
      </div>`;
    }).join("") || empty(t("empty.reviewed", "暂无已审查记录")));

    const pending = listOf(data.pending).filter(isRecord);
    setHtml("persona-pending-list", pending.map((item) => reviewCardHtml(item, "persona")).join("")
      || empty(t("persona.pendingEmpty", "没有待审人格更新")));
    showErrors(data.errors || {});
  }

  // ── 影子模式（对齐独立版 ShadowModePage） ──
  function shadowGroupsOf(data) {
    const groups = ((data || {}).sources || {})[state.shadow.source];
    return Array.isArray(groups) ? groups.filter(isRecord) : [];
  }

  // 生效群组默认跟随来源群组；用户手动改过（与上一次来源群组不同）时保留输入
  function syncShadowTarget(previousGroup) {
    const input = $("shadow-target-group");
    const current = ((input ? input.value : state.shadow.targetGroupId) || "").trim();
    if (!current || current === previousGroup) {
      state.shadow.targetGroupId = state.shadow.groupId;
      if (input) input.value = state.shadow.groupId;
    }
  }

  function shadowMinSamplesText() {
    return fill(t("shadow.minSamples", "至少需要 {count} 条有效文本"), { count: state.shadow.minimumSamples });
  }

  async function loadShadowMode(force, options = {}) {
    let data;
    try {
      data = await cached("shadow-mode", () => apiGet("shadow-mode"), force);
    } catch (error) {
      showToast(error.message || t("shadow.statusFailed", "读取影子模式状态失败"), "error");
      return;
    }
    if (data && data.success === false) {
      showToast(data.message || t("shadow.statusFailed", "读取影子模式状态失败"), "error");
    }
    if (!state.shadow.initialized) {
      // 与独立版一致：首次进入时有现有群聊记录则选现有群聊，否则选导入记录
      const live = ((data || {}).sources || {}).live;
      state.shadow.source = Array.isArray(live) && live.length ? "live" : "imported";
      state.shadow.initialized = true;
    }
    renderShadowMode(data || {}, options);
    await loadShadowCandidates(force);
  }

  function renderShadowMode(data, options = {}) {
    state.shadow.statusData = data || {};
    state.shadow.profiles = Array.isArray(data.profiles) ? data.profiles : [];
    state.shadow.minimumSamples = Number(data.minimum_samples) || 3;
    setText("shadow-min-samples", shadowMinSamplesText());
    setText("shadow-profile-count", fmt(state.shadow.profiles.length, 0));
    qsa("#shadow-source button").forEach((btn) => btn.classList.toggle("active", btn.dataset.shadowSource === state.shadow.source));
    const groups = shadowGroupsOf(data);
    const previousGroup = state.shadow.groupId;
    if (options.resetGroup || !groups.some((group) => String(group.group_id) === state.shadow.groupId)) {
      state.shadow.groupId = groups.length ? String(groups[0].group_id ?? "") : "";
    }
    syncShadowTarget(previousGroup);
    const groupSelect = $("shadow-group");
    if (groupSelect) {
      groupSelect.innerHTML = groups.map((group) => `<option value="${escapeAttr(group.group_id)}">${escapeHtml(fill(t("shadow.groupOption", "{group} · {count} 人"), {
        group: group.group_id,
        count: fmt(group.member_count, 0),
      }))}</option>`).join("");
      groupSelect.disabled = !groups.length;
      groupSelect.value = state.shadow.groupId;
    }
    renderShadowProfiles();
    refreshShadowLearnState();
  }

  function renderShadowProfiles() {
    const rows = state.shadow.profiles;
    setHtml("shadow-profile-list", rows.map((profile) => `
      <div class="table-row rich-row shadow-profile-row">
        <div>
          <strong>${escapeHtml(profile.sender_name || profile.sender_id || `#${profile.id}`)}</strong>
          <small>QQ ${escapeHtml(profile.sender_qq || profile.sender_id || "-")} · ${escapeHtml(profile.source_type === "imported" ? t("shadow.importedSource", "导入记录") : t("shadow.liveSource", "现有群聊"))} · ${escapeHtml(t("units.samples", "{count} 条样本").replace("{count}", fmt(profile.sample_count, 0)))}</small>
        </div>
        <div class="profile-scope">
          <span>${escapeHtml(t("shadow.targetGroup", "生效群组"))}</span>
          <strong>${escapeHtml(profile.target_group_id || "-")}</strong>
          <small>${escapeHtml(formatTime(profile.updated_at))}</small>
        </div>
        ${pill(profile.enabled ? t("state.enabled", "启用") : t("state.closed", "关闭"), profile.enabled ? "ok" : "warn")}
        <div class="row-actions">
          ${button(profile.enabled ? t("actions.disable", "停用") : t("actions.enable", "启用"), `data-shadow-profile-action="${profile.enabled ? "disable" : "enable"}" data-id="${escapeAttr(profile.id)}"`, profile.enabled ? "ghost-button warning-button" : "ghost-button success-button")}
        </div>
      </div>
    `).join("") || empty(t("empty.shadowProfiles", "尚未创建影子档案")));
  }

  async function loadShadowCandidates(force) {
    if (!state.shadow.groupId) {
      state.shadow.candidates = [];
      state.shadow.selectedId = "";
      setHtml("shadow-candidate-list", empty(state.shadow.source === "live"
        ? t("shadow.noLiveGroups", "暂无现有群聊记录")
        : t("shadow.noImportedGroups", "暂无已导入聊天记录")));
      refreshShadowLearnState();
      return;
    }
    const params = { source: state.shadow.source, group_id: state.shadow.groupId };
    let data = {};
    try {
      data = await cached(`shadow-candidates:${JSON.stringify(params)}`, () => apiGet("shadow-mode/candidates", params), force);
    } catch (error) {
      showToast(error.message || t("shadow.candidatesFailed", "读取群友列表失败"), "error");
    }
    if (data && data.success === false) {
      showToast(data.message || t("shadow.candidatesFailed", "读取群友列表失败"), "error");
    }
    state.shadow.minimumSamples = Number((data || {}).minimum_samples) || 3;
    setText("shadow-min-samples", shadowMinSamplesText());
    state.shadow.selectedId = "";
    state.shadow.candidates = Array.isArray((data || {}).candidates) ? data.candidates.filter(isRecord) : [];
    renderShadowCandidates(state.shadow.candidates);
    refreshShadowLearnState();
  }

  function renderShadowCandidates(candidates) {
    setHtml("shadow-candidate-list", candidates.map((candidate) => {
      const senderId = String(candidate.sender_id ?? "");
      const selected = state.shadow.selectedId === senderId;
      return `<button class="candidate-row ${selected ? "selected" : ""}" type="button"
        data-shadow-candidate="${escapeAttr(senderId)}" ${candidate.ready ? "" : "disabled"}
        aria-pressed="${selected}">
        <span class="candidate-copy"><strong>${escapeHtml(candidate.sender_name || senderId)}</strong><small>QQ ${escapeHtml(candidate.sender_qq || senderId || "-")}</small></span>
        <span class="candidate-meta"><b>${escapeHtml(fmt(candidate.message_count, 0))}</b><small>${escapeHtml(t("shadow.messagesUnit", "条消息"))}</small></span>
        ${pill(candidate.ready ? t("shadow.learnable", "可学习") : t("shadow.insufficient", "样本不足"), candidate.ready ? "ok" : "warn")}
      </button>`;
    }).join("") || empty(t("empty.shadowCandidates", "这个群组暂无可选用户")));
  }

  function refreshShadowLearnState() {
    const hasSelection = Boolean(state.shadow.selectedId);
    setText("shadow-learn-hint", hasSelection
      ? t("shadow.learnHint", "将重新分析目标用户的全部有效文本，并替换该群组当前影子。")
      : t("shadow.pickFirst", "选择用户后即可开始学习。"));
    const learn = $("shadow-learn-button");
    if (learn && !learn.classList.contains("is-busy")) learn.disabled = !hasSelection;
  }

  async function handleShadowLearn() {
    const candidate = (state.shadow.candidates || []).find((item) => String(item.sender_id ?? "") === state.shadow.selectedId);
    if (!candidate) {
      showToast(t("shadow.pickCandidate", "请先选择一位可学习的群友"), "warn");
      return;
    }
    const targetGroup = ($("shadow-target-group")?.value || "").trim();
    if (!targetGroup) {
      showToast(t("shadow.missingTarget", "请输入影子模式的生效群组"), "warn");
      return;
    }
    const learn = $("shadow-learn-button");
    try {
      if (learn) { learn.disabled = true; learn.classList.add("is-busy"); }
      const result = await apiPost("shadow-mode/action", {
        action: "learn",
        source_type: state.shadow.source,
        source_group_id: state.shadow.groupId,
        target_group_id: targetGroup,
        sender_id: candidate.sender_id,
        activate: true,
      });
      if (result.success === false) {
        showToast(result.message || t("shadow.learnFailed", "影子学习失败"), "error");
        return;
      }
      showToast(fill(t("shadow.learnedToast", "已学习并启用 {name} 的影子模式"), { name: candidate.sender_name || "" }), "ok");
      state.shadow.targetGroupId = targetGroup;
      clearCached("shadow-mode");
      clearCached("shadow-candidates");
      await loadShadowMode(true);
    } catch (error) {
      showToast(error.message || t("shadow.learnFailed", "影子学习失败"), "error");
    } finally {
      if (learn) learn.classList.remove("is-busy");
      refreshShadowLearnState();
    }
  }

  async function handleShadowProfileAction(buttonEl) {
    const enabled = buttonEl.dataset.shadowProfileAction === "enable";
    try {
      const result = await apiPost("shadow-mode/action", {
        action: "set_enabled",
        profile_id: buttonEl.dataset.id,
        enabled,
      });
      if (result.success === false) {
        showToast(result.message || t("shadow.updateFailed", "更新影子模式失败"), "error");
        return;
      }
      showToast(enabled ? t("shadow.enabledToast", "影子模式已启用") : t("shadow.disabledToast", "影子模式已停用"), "ok");
    } catch (error) {
      showToast(error.message || t("shadow.updateFailed", "更新影子模式失败"), "error");
      return;
    }
    clearCached("shadow-mode");
    clearCached("shadow-candidates");
    await loadShadowMode(true);
  }

  function formatTimestamp(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) return String(value || "");
    const ms = num < 1e12 ? num * 1000 : num;
    try {
      return new Date(ms).toLocaleString(locale());
    } catch (_) {
      return String(value);
    }
  }

  // ── 学习内容（对齐独立版 ContentPage：内容浏览器 + 分类检索 + 删除确认） ──
  async function loadContent(force) {
    const data = await cached("content", () => apiGet("content", { page: 1, page_size: 10 }), force);
    renderContent(data);
  }

  function renderContent(data) {
    state.pageData.content = data;
    const content = data.content || {};
    qsa("#content-tabs button").forEach((btn) => btn.classList.toggle("active", btn.dataset.contentType === state.contentType));
    const query = String(state.contentQuery || "").toLowerCase();
    const items = listOf(content[state.contentType]).filter(isRecord)
      .filter((item) => !query || summarize(item).toLowerCase().includes(query));
    setHtml("learning-content-list", items.map((item) => `<details class="content-entry">
        <summary><strong>${escapeHtml(textOrDash(item.title ?? item.name ?? item.id ?? t("content.itemFallback", "内容项")))}</strong><span class="content-entry-arrow" aria-hidden="true">▾</span></summary>
        <pre class="code-preview">${escapeHtml(summarize(item))}</pre>
        ${button(t("actions.delete", "删除"), `data-content-action="delete_content" data-bucket="${escapeAttr(state.contentType)}" data-id="${escapeAttr(item.id ?? item.uuid ?? "")}"`, "danger-button")}
      </details>`).join("") || empty(t("content.empty", "当前分类暂无内容")));
    showErrors(data.errors || {});
  }

  async function loadGraphs(force) {
    const type = $("graph-type")?.value || "memory";
    const group = ($("graph-group")?.value || "").trim();
    state.graph.type = type;
    const params = { type, limit: 140 };
    if (group) params.group_id = group;
    const data = await cached(`graphs:${type}:${group}`, () => apiGet("graphs", params), force);
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
      [t("graphs.stats.nodes", "节点"), (graph.stats || {}).nodes || state.graph.nodes.length],
      [t("graphs.stats.links", "连线"), (graph.stats || {}).links || state.graph.links.length],
      [t("graphs.stats.groups", "群组"), (graph.stats || {}).groups || (graph.groups || []).length],
      [t("graphs.stats.source", "来源"), graph.data_source || "self_learning"],
    ]));
    setHtml("graph-node-list", state.graph.nodes.slice(0, 18).map((node) => `
      <div class="table-row">
        <span>${escapeHtml(node.name || node.id)}</span>
        <strong>${escapeHtml(node.category_name || node.category || t("graphs.node", "节点"))}</strong>
        <small>${escapeHtml(node.detail || "")}</small>
      </div>
    `).join("") || empty(t("empty.graphNodes", "暂无图谱节点")));
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

  function renderIntegrations(data) {
    setHtml("integration-cards", (data.dashboards || []).map(integrationCardHtml).join("") || empty(t("empty.integrations", "暂无融合状态")));
    setHtml("integration-warnings", warningListHtml(data.warnings || []));
    const settings = data.settings || {};
    setHtml("integration-settings", Object.entries(settings).map(([key, value]) => `
      <div class="table-row">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(value === true ? t("state.on", "开启") : value === false ? t("state.off", "关闭") : value ?? t("state.unset", "未设置"))}</strong>
      </div>
    `).join("") || empty(t("empty.integrationSettings", "暂无融合设置")));
    renderMaiBotImportPreview(data.maibot_learning || null);
    loadWorldbookHistory();
  }

  function integrationCardHtml(item) {
    const dash = item.dashboard || {};
    const status = item.status || {};
    const url = resolveHostUrl(dash.external_url || dash.official_page_url || "#");
    const disabled = !dash.available || !url || url === "#";
    const stateText = status.healthy === true ? t("state.healthy", "正常")
      : status.healthy === false ? t("state.unhealthy", "异常")
      : item.active ? t("state.available", "可用") : t("state.disabled", "未启用");
    return `<article class="integration-card ${item.active ? "active" : ""}">
      <div>
        <span>${escapeHtml(item.role || "")}</span>
        <h3>${escapeHtml(item.title || item.id)}</h3>
        <p>${escapeHtml(item.delegated ? t("state.delegated", "已委托") : stateText)}</p>
        ${status.message ? `<small>${escapeHtml(String(status.message))}</small>` : ""}
      </div>
      <a class="ghost-button ${disabled ? "disabled" : ""}" href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${escapeHtml(dash.label || t("actions.open", "打开"))}</a>
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
      throw new Error(t("maibot.missingPath", "请填写 MaiBot 项目目录或主数据库路径"));
    }
    return payload;
  }

  function collectQchatPayload() {
    const payload = {
      source_path: $("qchat-source-input")?.value?.trim() || "",
      default_group_id: $("qchat-default-group-input")?.value?.trim() || "",
      max_messages: Math.max(1, parseInt($("qchat-max-messages-input")?.value || "100000", 10) || 100000),
      include_training_pairs: Boolean($("qchat-include-training")?.checked),
    };
    if (!payload.source_path) {
      throw new Error(t("qchat.missingPath", "请填写 QQ 聊天记录路径"));
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
      lines.push(t("maibot.previewCounts", "预览: 表达 {expressions} · 黑话 {jargons} · 记忆 {memories}")
        .replace("{expressions}", fmt(counts.expressions, 0))
        .replace("{jargons}", fmt(counts.jargons, 0))
        .replace("{memories}", fmt(counts.memories, 0)));
    }
    if (Object.keys(breakdown).length) {
      lines.push(t("maibot.importCounts", "导入: 表达审查 {style} · 黑话候选 {jargon} · 记忆审查 {memory}")
        .replace("{style}", fmt(breakdown.style_learning_reviews, 0))
        .replace("{jargon}", fmt(breakdown.jargon_candidates, 0))
        .replace("{memory}", fmt(breakdown.persona_memory_reviews, 0)));
    }
    if (Object.keys(destinations).length) {
      lines.push(t("maibot.destinations", "分类去向: 表达 -> {expressions}; 黑话 -> {jargons}; 记忆 -> {memories}")
        .replace("{expressions}", destinations.expressions)
        .replace("{jargons}", destinations.jargons)
        .replace("{memories}", destinations.memories));
    }
    output.textContent = `${lines.join("\n")}${lines.length ? "\n\n" : ""}${JSON.stringify(summary, null, 2)}`;
  }

  function renderQchatImportPreview(summary) {
    const output = $("qchat-import-output");
    if (!output || !summary) return;
    const counts = summary.counts || {};
    const lines = [];
    if (Object.keys(counts).length) {
      lines.push(t("qchat.previewCounts", "预览: 消息 {messages} · Bot {bot} · 发送者 {senders}")
        .replace("{messages}", fmt(counts.messages, 0))
        .replace("{bot}", fmt(counts.bot_messages, 0))
        .replace("{senders}", fmt(counts.unique_senders, 0)));
      lines.push(t("qchat.tokenCounts", "字符 {chars} · 预估 Tokens {tokens}")
        .replace("{chars}", fmt(counts.content_chars, 0))
        .replace("{tokens}", fmt(counts.estimated_tokens, 0)));
    }
    if (summary.messages_imported !== undefined || summary.messages_seen !== undefined) {
      lines.push(t("qchat.importCounts", "导入: 扫描 {seen} · 写入 {imported} · 重复 {duplicates}")
        .replace("{seen}", fmt(summary.messages_seen, 0))
        .replace("{imported}", fmt(summary.messages_imported, 0))
        .replace("{duplicates}", fmt(summary.duplicate_messages, 0)));
    }
    const destinations = summary.destinations || {};
    if (Object.keys(destinations).length) {
      lines.push(t("qchat.destinations", "去向: 原始消息 -> {raw}; 学习队列 -> {queue}")
        .replace("{raw}", destinations.raw_messages || "raw_messages")
        .replace("{queue}", destinations.learning_queue || "raw_messages.processed=false"));
    }
    output.textContent = `${lines.join("\n")}${lines.length ? "\n\n" : ""}${JSON.stringify(summary, null, 2)}`;
  }

  function collectWorldbookPayload() {
    const raw = ($("worldbook-json-input")?.value || "").trim();
    if (!raw) {
      throw new Error(t("worldbook.missingJson", "请先填写世界书 JSON"));
    }
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      throw new Error(t("worldbook.invalidJson", "世界书 JSON 格式无效"));
    }
    return {
      payload,
      default_group_id: ($("worldbook-group-input")?.value || "").trim() || "global",
      import_memories: Boolean($("worldbook-import-memories")?.checked),
      import_jargons: Boolean($("worldbook-import-jargons")?.checked),
      import_knowledge_graph: Boolean($("worldbook-import-knowledge")?.checked),
      include_disabled: Boolean($("worldbook-include-disabled")?.checked),
    };
  }

  function renderWorldbookPreview(detail) {
    const output = $("worldbook-import-output");
    if (!output) return;
    const counts = detail.counts || {};
    const breakdown = detail.review_breakdown || {};
    const lines = [];
    if (detail.name) lines.push(t("worldbook.name", "世界书：{name}").replace("{name}", detail.name));
    if (Object.keys(counts).length) {
      lines.push(t("worldbook.previewCounts", "预览: 条目 {entries}（启用 {enabled} / 禁用 {disabled}）· 关键词 {keywords}")
        .replace("{entries}", fmt(counts.entries, 0))
        .replace("{enabled}", fmt(counts.enabled_entries, 0))
        .replace("{disabled}", fmt(counts.disabled_entries, 0))
        .replace("{keywords}", fmt(counts.keywords, 0)));
      lines.push(t("worldbook.tokenCounts", "字符 {chars} · 预估 Tokens {tokens}")
        .replace("{chars}", fmt(counts.content_chars, 0))
        .replace("{tokens}", fmt(counts.estimated_tokens, 0)));
    }
    if (Object.keys(breakdown).length) {
      lines.push(t("worldbook.breakdown", "去向: 记忆审查 {memory} · 黑话候选 {jargon} · 图谱实体 {entities}")
        .replace("{memory}", fmt(breakdown.persona_memory_reviews, 0))
        .replace("{jargon}", fmt(breakdown.jargon_candidates, 0))
        .replace("{entities}", fmt(breakdown.knowledge_graph_entities, 0)));
    }
    if (detail.entries_imported !== undefined) {
      lines.push(t("worldbook.importCounts", "导入: 条目 {entries} · 记忆 {memory} · 黑话 {jargon} · 图谱实体/关系 {entities}/{relations} · 跳过 {skipped}")
        .replace("{entries}", fmt(detail.entries_imported, 0))
        .replace("{memory}", fmt(detail.memory_reviews_imported, 0))
        .replace("{jargon}", fmt(detail.jargons_imported, 0))
        .replace("{entities}", fmt(detail.kg_entities_imported, 0))
        .replace("{relations}", fmt(detail.kg_relations_imported, 0))
        .replace("{skipped}", fmt(detail.skipped, 0)));
    }
    output.textContent = `${lines.join("\n")}${lines.length ? "\n\n" : ""}${JSON.stringify(detail, null, 2)}`;
  }

  async function loadWorldbookHistory() {
    try {
      const result = await apiPost("integrations/action", { action: "worldbook_history", limit: 8 });
      const history = result.history || {};
      const imports = history.imports || {};
      const rows = Object.values(imports)
        .sort((a, b) => String(b.imported_at || b.created_at || "").localeCompare(String(a.imported_at || a.created_at || "")))
        .slice(0, 8);
      setHtml("worldbook-history-list", rows.length ? `
        <div class="table-row history-heading">
          <strong>${escapeHtml(t("worldbook.recentImports", "最近导入记录"))}</strong>
        </div>
        ${rows.map((item) => `
          <div class="table-row">
            <div>
              <strong>${escapeHtml(item.worldbook_name || item.source_name || item.import_id || t("worldbook.defaultName", "世界书导入"))}</strong>
              <small>${escapeHtml(formatTimestamp(item.imported_at || item.created_at))}</small>
            </div>
            <strong>${escapeHtml(fmt(item.entries, 0))}</strong>
            ${pill(String(item.status ?? ""), item.status === "approved" || item.status === "success" ? "ok" : "warn")}
          </div>
        `).join("")}` : "");
    } catch (_) {
      setHtml("worldbook-history-list", "");
    }
  }

  async function runWorldbookAction(action) {
    const buttonEl = action === "worldbook_import" ? $("worldbook-import-button") : $("worldbook-preview-button");
    const originalLabel = buttonEl?.textContent || "";
    try {
      const payload = collectWorldbookPayload();
      if (action === "worldbook_import") {
        const confirmed = await showConfirm(
          t("modal.confirmImport", "确认导入"),
          t("worldbook.confirmImport", "将写入人格审查、黑话候选或知识图谱，确定继续吗？"),
          t("actions.import", "导入"),
        );
        if (!confirmed) return;
      }
      if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.classList.add("is-busy");
        buttonEl.textContent = action === "worldbook_import" ? t("actions.importing", "导入中") : t("actions.previewing", "预览中");
      }
      setText("worldbook-import-output", action === "worldbook_import" ? t("worldbook.importing", "正在导入世界书...") : t("worldbook.previewing", "正在解析世界书..."));
      const result = await apiPost("integrations/action", { action, ...payload });
      const detail = result.preview || result.result || result.payload || result;
      renderWorldbookPreview(detail);
      showToast(result.message || t("worldbook.done", "世界书操作完成"), result.success !== false ? "ok" : "error");
      if (action === "worldbook_import") {
        state.pageData = {};
        await loadDashboard(true);
        await loadWorldbookHistory();
      }
    } catch (error) {
      const message = error.message || String(error);
      setText("worldbook-import-output", message);
      showToast(message, "error");
    } finally {
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.classList.remove("is-busy");
        buttonEl.textContent = originalLabel;
      }
    }
  }

  function renderQchatSenders() {
    const senders = (state.qchatPreviewData || {}).senders || [];
    const container = $("qchat-sender-list");
    if (!container) return;
    if (!senders.length) {
      container.replaceChildren();
      return;
    }
    container.innerHTML = `
      <div class="sender-heading">
        <strong>${escapeHtml(t("qchat.senders", "导入记录中的用户"))}</strong>
        <span>${escapeHtml(t("qchat.sendersHint", "{count} 人 · 选择一人可在导入后立即启用影子模式").replace("{count}", fmt(senders.length, 0)))}</span>
      </div>
      <div class="sender-grid">
        ${senders.map((sender) => {
          const senderId = String(sender.sender_id ?? "");
          const count = Number(sender.message_count) || 0;
          const learnable = count >= 3;
          return `<button class="sender-row ${state.qchatShadowSender === senderId ? "selected" : ""}" type="button"
            data-qchat-sender="${escapeAttr(senderId)}" ${learnable ? "" : "disabled"}>
            <strong>${escapeHtml(sender.sender_name || senderId)}</strong>
            <small>QQ ${escapeHtml(sender.sender_qq || senderId)}</small>
            <b>${escapeHtml(fmt(count, 0))}</b>
            <small>${escapeHtml(learnable ? t("shadow.learnable", "可学习") : t("shadow.insufficient", "样本不足"))}</small>
          </button>`;
        }).join("")}
      </div>
    `;
    updateQchatImportButton();
  }

  function updateQchatImportButton() {
    const buttonEl = $("qchat-import-button");
    if (!buttonEl) return;
    buttonEl.textContent = state.qchatShadowSender
      ? t("qchat.importWithShadow", "导入并启用影子")
      : t("actions.import", "导入");
  }

  async function runMaiBotImportAction(action) {
    const buttonEl = action === "maibot_import" ? $("maibot-import-button") : $("maibot-preview-button");
    const originalLabel = buttonEl?.textContent || "";
    try {
      const payload = collectMaiBotPayload();
      if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.classList.add("is-busy");
        buttonEl.textContent = action === "maibot_import" ? t("actions.importing", "导入中") : t("actions.previewing", "预览中");
      }
      setText("maibot-import-output", t("maibot.reading", "正在读取 MaiBot 学习数据..."));
      const result = await apiPost("integrations/action", { action, ...payload });
      const detail = result.preview || result.result || result.payload || result;
      renderMaiBotImportPreview(detail);
      showToast(result.message || t("maibot.done", "MaiBot 学习数据操作完成"), result.success !== false ? "ok" : "error");
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

  async function runQchatImportAction(action) {
    const buttonEl = action === "qchat_import" ? $("qchat-import-button") : $("qchat-preview-button");
    const originalLabel = buttonEl?.textContent || "";
    try {
      const payload = collectQchatPayload();
      if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.classList.add("is-busy");
        buttonEl.textContent = action === "qchat_import" ? t("actions.importing", "导入中") : t("actions.previewing", "预览中");
      }
      setText("qchat-import-output", t("qchat.reading", "正在读取 QQ 聊天记录..."));
      const result = await apiPost("integrations/action", { action, ...payload });
      const detail = result.preview || result.result || result.payload || result;
      renderQchatImportPreview(detail);
      if (action === "qchat_preview") {
        state.qchatPreviewData = detail;
        state.qchatShadowSender = "";
        const groupInput = $("qchat-default-group-input");
        if (groupInput && !groupInput.value.trim() && detail.group_id && detail.group_id !== "global") groupInput.value = String(detail.group_id);
        renderQchatSenders();
        showToast(result.message || t("qchat.previewDone", "预览完成，可从用户列表选择影子对象"), "ok");
        return;
      }
      showToast(result.message || t("qchat.done", "QQ 聊天记录操作完成"), result.success !== false ? "ok" : "error");
      if (action === "qchat_import" && state.qchatShadowSender) {
        try {
          const senderId = state.qchatShadowSender;
          const sender = ((state.qchatPreviewData || {}).senders || [])
            .find((item) => String(item.sender_id ?? "") === senderId);
          const shadowResult = await apiPost("shadow-mode/action", {
            action: "learn",
            source_type: "imported",
            source_group_id: String(detail.group_id || payload.default_group_id || ""),
            target_group_id: payload.default_group_id || String(detail.group_id || ""),
            sender_id: senderId,
            activate: true,
          });
          showToast(t("qchat.shadowLearned", "已启用 {name} 的影子模式").replace("{name}", sender?.sender_name || senderId), shadowResult.success ? "ok" : "error");
        } catch (shadowError) {
          showToast(t("qchat.shadowFailed", "聊天记录已导入，但影子学习失败：{reason}").replace("{reason}", shadowError.message || String(shadowError)), "error");
        }
      }
      if (action === "qchat_import") {
        state.pageData = {};
        await loadDashboard(true);
      }
    } catch (error) {
      const message = error.message || String(error);
      setText("qchat-import-output", message);
      showToast(message, "error");
    } finally {
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.classList.remove("is-busy");
        buttonEl.textContent = originalLabel;
      }
      updateQchatImportButton();
    }
  }

  function renderSettings(data) {
    const schema = data.schema || {};
    setHtml("settings-warnings", warningListHtml(schema.warnings || data.warnings || []));
    const groups = schema.groups || [];
    if (!state.settingsGroup && groups.length) state.settingsGroup = groups[0].key;
    setHtml("settings-groups", groups.map((group) => `
      <button class="settings-group ${group.key === state.settingsGroup ? "active" : ""}" type="button" data-settings-group="${escapeAttr(group.key)}">
        <strong>${escapeHtml(configT(`${group.key}.description`, group.title || group.key))}</strong>
        <small>${escapeHtml(configT(`${group.key}.hint`, group.hint || ""))}</small>
      </button>
    `).join("") || empty(t("empty.configSchema", "配置 schema 暂不可用")));

    const active = groups.find((group) => group.key === state.settingsGroup) || groups[0] || { fields: [] };
    setHtml("config-form", (active.fields || []).map(fieldHtml).join("") || empty(t("empty.selectConfigGroup", "请选择配置分组")));
    renderPipMirrors(data.pip_mirrors || {});
  }

  function fieldHtml(field) {
    const value = state.dirtySettings.has(field.key) ? state.dirtySettings.get(field.key) : field.value;
    const common = `data-config-field="${escapeAttr(field.key)}" data-config-type="${escapeAttr(field.type)}" ${field.editable ? "" : "disabled"}`;
    const groupKey = field.group_key || activeSettingsGroupKeyForField(field.key);
    const label = configT(`${groupKey}.${field.key}.description`, field.label || field.key);
    const hint = configT(`${groupKey}.${field.key}.hint`, field.hint || "");
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
        <strong>${escapeHtml(label)}</strong>
        <small>${escapeHtml(hint)}${field.restart_required ? t("settings.restartRequired", " · 重启后生效") : ""}</small>
      </span>
      ${control}
    </label>`;
  }

  function activeSettingsGroupKeyForField(fieldKey) {
    const groups = ((state.pageData.settings || {}).schema || {}).groups || [];
    const group = groups.find((item) => (item.fields || []).some((field) => field.key === fieldKey));
    return group?.key || state.settingsGroup || "";
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

  // ── 总览（对齐独立版 OverviewPage：4 读数 + 消息/学习趋势 + 当前状态） ──
  function renderOverview(data) {
    const metrics = (data && data.metrics) || {};
    const total = Number(metrics.total_messages_collected || 0);
    const rawEfficiency = Number(metrics.learning_efficiency ?? metrics.efficiency ?? 0);
    const efficiency = rawEfficiency <= 1 ? rawEfficiency * 100 : rawEfficiency;
    const filtered = Number(metrics.filtered_messages ?? (metrics.messages || {}).filtered ?? 0);
    const memory = Number((metrics.system_metrics || {}).memory_percent || 0);
    setText("ov-stat-messages", fmt(total, 0));
    setText("ov-stat-efficiency", `${fmt(efficiency, 1)}%`);
    setText("ov-stat-filtered", fmt(filtered, 0));
    setText("ov-stat-memory", `${fmt(memory, 1)}%`);

    const trends = metrics.trends || (data && data.trends) || {};
    const daily = trends.daily_messages || {};
    const labels = Object.keys(daily).sort().slice(-14);
    const items = labels.map((label) => ({
      title: String(label).slice(5),
      metric: Number(daily[label] || 0),
      accent: "var(--chart-1)",
    }));
    renderGenericBarChart("ov-trend-chart", items);
    const batches = Array.isArray(trends.recent_batches) ? trends.recent_batches : [];
    const learned = batches.reduce((sum, batch) => sum + Number(batch.processed_messages ?? batch.message_count ?? 0), 0);
    setText("ov-trend-note", items.length
      ? t("overview.trendNote", "近 {days} 天采集 {count} 条消息 · 学习处理 {learned} 条。")
        .replace("{days}", fmt(items.length, 0))
        .replace("{count}", fmt(items.reduce((sum, item) => sum + item.metric, 0), 0))
        .replace("{learned}", fmt(learned, 0))
      : t("home.noTrends", "暂无趋势数据，积累消息后这里会出现每日采集曲线。"));
  }

  // ── 情绪中枢（对齐独立版 EmotionBoardPage） ──
  const MOOD_OPTIONS = ["happy", "excited", "playful", "calm", "curious", "nostalgic", "serious", "anxious", "sad", "angry"];
  const MOOD_FALLBACK = {
    happy: "开心", excited: "兴奋", playful: "顽皮", calm: "平静", curious: "好奇",
    nostalgic: "怀旧", serious: "严肃", anxious: "焦虑", sad: "低落", angry: "生气",
  };
  const FACTOR_FALLBACK = { affection: "好感度", sentiment: "消息情感", mood: "Bot 心情", stability: "情绪稳定性" };
  const KIND_FALLBACK = { expression: "表达", jargon: "黑话" };

  const moodLabel = (type) => t(`emotion.moods.${type}`, MOOD_FALLBACK[type] || type);
  const factorLabel = (key) => t(`emotion.factors.${key}`, FACTOR_FALLBACK[key] || key);
  const kindLabel = (kind) => t(`emotion.kinds.${kind}`, KIND_FALLBACK[kind] || kind);
  // 心情语气：正向=ok（状态绿），负向=warn，其余中性（与独立版 moodTone 同规则）
  const moodTone = (type) => ["happy", "excited", "playful"].includes(type) ? "ok"
    : ["sad", "anxious", "angry"].includes(type) ? "warn" : "";
  const fmtPct = (value) => `${fmt(Number(value || 0) <= 1 ? Number(value || 0) * 100 : Number(value || 0), 1)}%`;

  async function loadEmotion(force) {
    const [board, trends] = await Promise.all([
      cached("emotion:board", () => apiGet("emotion/board"), force),
      cached("emotion:trends", () => apiGet("emotion/trends", { days: 14 }), force),
    ]);
    renderEmotion(board || {}, trends || {});
  }

  function emotionCandidates(forgetting) {
    const data = (forgetting && forgetting.candidates) || {};
    return [...(data.expression || []), ...(data.jargon || [])]
      .sort((a, b) => Number(b.stage || 0) - Number(a.stage || 0) || Number(a.last_used || 0) - Number(b.last_used || 0));
  }

  function renderEmotion(board, trends) {
    state.emotion = { board, trends };
    const moods = ((board.moods || {}).active) || [];
    const affection = board.affection || null;
    const gateDaily = trends.gate || [];
    const gateToday = gateDaily.length ? gateDaily[gateDaily.length - 1] : null;
    const telemetry = (board.gate || {}).telemetry || null;
    const forgetting = board.forgetting || null;
    const candidates = emotionCandidates(forgetting);

    // 读数行
    setText("emo-stat-mood", moods[0] ? moodLabel(moods[0].mood_type) : "--");
    setText("emo-stat-mood-note", moods.length
      ? t("emotion.activeGroups", "{count} 个群组有活跃心情").replace("{count}", fmt(moods.length, 0))
      : t("emotion.noActiveMood", "暂无活跃心情"));
    const overall = (affection && affection.overall) || {};
    setText("emo-stat-affection", fmt(overall.average || 0, 1));
    setText("emo-stat-affection-note", t("emotion.userCount", "{count} 位用户").replace("{count}", fmt(overall.total_users || 0, 0)));
    setText("emo-stat-gate", gateToday && gateToday.accept_rate != null ? fmtPct(gateToday.accept_rate) : "--");
    setText("emo-stat-gate-note", telemetry && telemetry.enabled
      ? t("emotion.gateThreshold", "阈值 {value}").replace("{value}", String(telemetry.threshold))
      : t("emotion.gateDisabled", "闸门未启用"));
    setText("emo-stat-forget", fmt(candidates.length, 0));
    setText("emo-stat-forget-note", forgetting && forgetting.enabled
      ? t("emotion.cycleDays", "周期 {days} 天").replace("{days}", fmt((forgetting.config || {}).cycle_days || 0, 0))
      : t("emotion.forgetDisabled", "遗忘未启用"));

    // Bot 心情状态
    setHtml("emo-mood-list", moods.length ? moods.map((mood) => `
      <div class="review-item">
        <div class="table-row rich-row" style="padding:0;border:0;background:transparent;">
          <div>
            <strong>${escapeHtml(mood.group_id || "--")}</strong>
            <small>${escapeHtml(mood.description || "--")} · ${escapeHtml(formatTimestamp(mood.timestamp))}</small>
          </div>
          ${pill(moodLabel(mood.mood_type), moodTone(mood.mood_type))}
        </div>
        <div class="bar-row" style="--accent:var(--chart-2)">
          <span>${escapeHtml(t("emotion.intensity", "强度"))} ${escapeHtml(fmtPct(mood.intensity))}</span>
          <div class="bar-track"><div class="bar-fill" style="--value:${Math.max(0, Math.min(100, Number(mood.intensity || 0) * 100))}"></div></div>
          <strong></strong>
        </div>
      </div>`).join("") : empty(t("emotion.noActiveMoodDetail", "暂无活跃心情：可在下方手动设置，或等待每日情绪更新。")));

    const typeSelect = $("emo-mood-type");
    if (typeSelect && !typeSelect.options.length) {
      typeSelect.innerHTML = MOOD_OPTIONS.map((option) => `<option value="${escapeAttr(option)}">${escapeHtml(moodLabel(option))}</option>`).join("");
    }
    syncMoodFillButton();

    // 好感度概览
    if (affection) {
      setHtml("emo-affection-list", (affection.groups || []).map((group) => `
        <div class="table-row rich-row">
          <div>
            <strong>${escapeHtml(group.group_id || "--")}</strong>
            <small>${escapeHtml(t("emotion.groupStats", "{users} 位用户 · 高好感 {high} · 低好感 {low}")
              .replace("{users}", fmt(group.total_users, 0)).replace("{high}", fmt(group.high, 0)).replace("{low}", fmt(group.low, 0)))}</small>
          </div>
          ${pill(fmt(group.average, 1), Number(group.average) >= 20 ? "ok" : Number(group.average) <= -20 ? "warn" : "")}
        </div>`).join("") || empty(t("emotion.noAffection", "暂无好感度数据")));
      const rankRow = (entry, positive) => `<div class="emo-rank-row"><span>${escapeHtml(entry.user_id)}</span><strong>${positive ? "+" : ""}${escapeHtml(fmt(entry.level, 0))}</strong></div>`;
      setHtml("emo-affection-top", (affection.leaderboard || []).map((entry) => rankRow(entry, true)).join("") || empty());
      setHtml("emo-affection-bottom", (affection.bottom || []).map((entry) => rankRow(entry, false)).join("") || empty());
    } else {
      setHtml("emo-affection-list", empty(t("emotion.noAffection", "暂无好感度数据")));
      setHtml("emo-affection-top", "");
      setHtml("emo-affection-bottom", "");
    }

    // 走向分析（4 组序列 = 独立版两张双序列图的展开）
    const delta = trends.affection_delta || [];
    const moodChanges = trends.mood_changes || [];
    renderGenericBarChart("emo-trend-affection", delta.map((item) => ({ title: String(item.date).slice(5), metric: Math.abs(Number(item.delta || 0)), accent: Number(item.delta || 0) >= 0 ? "var(--chart-1)" : "var(--danger)" })));
    renderGenericBarChart("emo-trend-mood", moodChanges.map((item) => ({ title: String(item.date).slice(5), metric: Number(item.count || 0), accent: "var(--chart-3)" })));
    renderGenericBarChart("emo-trend-gate", gateDaily.map((item) => ({ title: String(item.stat_date).slice(5), metric: Math.round(Number(item.accept_rate || 0) * 100), accent: "var(--chart-2)" })));
    renderGenericBarChart("emo-trend-score", gateDaily.map((item) => ({ title: String(item.stat_date).slice(5), metric: Math.round(Number(item.avg_score || 0) * 100), accent: "var(--chart-4)" })));
    const dist = ((board.emotion_profiles || {}).dominant_distribution) || [];
    const distBlock = $("emo-dist-block");
    if (distBlock) distBlock.hidden = !dist.length;
    setHtml("emo-dist-row", dist.map((item) => `<span class="mini-badge"><b>${escapeHtml(item.emotion)}</b>&nbsp;${escapeHtml(fmt(item.count, 0))}</span>`).join(""));

    // 学习联动 · 情绪加权闸门
    if (telemetry) {
      const accepted = Number((telemetry.counters || {}).accepted || 0);
      const skipped = Number((telemetry.counters || {}).skipped || 0);
      const total = accepted + skipped;
      const factorAvg = telemetry.recent_factor_avg || {};
      const weights = telemetry.weights || {};
      setHtml("emo-gate-body", `
        <div class="content-grid two-col">
          <div class="review-list">
            <div class="table-row rich-row"><div><strong>${escapeHtml(t("emotion.accepted", "累计放行"))}</strong><small>${escapeHtml(t("emotion.acceptedHint", "重启后计数归零，长期趋势看日统计"))}</small></div>${pill(fmt(accepted, 0), "ok")}</div>
            <div class="table-row rich-row"><div><strong>${escapeHtml(t("emotion.skipped", "累计拦截"))}</strong><small>${escapeHtml(t("emotion.skippedHint", "原始消息仍会采集，仅跳过学习"))}</small></div>${pill(fmt(skipped, 0), "warn")}</div>
            <div class="table-row rich-row"><div><strong>${escapeHtml(t("emotion.acceptRatio", "放行占比"))}</strong><small>${escapeHtml(t("emotion.sinceRun", "本次运行以来"))}</small></div>${pill(total ? fmtPct(accepted / total) : "--", total && skipped / total > 0.5 ? "warn" : "")}</div>
          </div>
          <div>
            <h4 class="mini-label">${escapeHtml(t("emotion.factorAvg", "近期因子均值"))}</h4>
            <div class="bar-chart">${Object.keys(factorAvg).map((key) => `
              <div class="bar-row" style="--accent:var(--chart-1)">
                <span>${escapeHtml(factorLabel(key))}（${escapeHtml(t("emotion.weight", "权重"))} ${escapeHtml(fmtPct(weights[key] || 0))}）</span>
                <div class="bar-track"><div class="bar-fill" style="--value:${Math.max(0, Math.min(100, Number(factorAvg[key] || 0) * 100))}"></div></div>
                <strong>${escapeHtml(fmtPct(factorAvg[key]))}</strong>
              </div>`).join("")}</div>
          </div>
        </div>
        <h4 class="mini-label" style="margin-top:14px;">${escapeHtml(t("emotion.recentDecisions", "近期判定"))}</h4>
        <div class="compact-table">${(telemetry.recent || []).slice(-10).reverse().map((item) => `
          <div class="table-row">
            <span>${escapeHtml(item.group_id)}</span>
            <small>${escapeHtml(formatTimestamp(item.timestamp))}</small>
            <strong>${escapeHtml(fmt(item.score, 2))}</strong>
            ${pill(item.decision ? t("emotion.pass", "放行") : t("emotion.block", "拦截"), item.decision ? "ok" : "warn")}
          </div>`).join("") || empty()}</div>`);
    } else {
      setHtml("emo-gate-body", empty(t("emotion.gateUnavailable", "闸门遥测不可用：插件运行中才会产生判定记录；历史统计见上方走向分析。")));
    }

    // 三阶段遗忘治理
    if (forgetting) {
      const stageLabels = forgetting.stage_labels || {};
      const distribution = forgetting.distribution || {};
      const config = forgetting.config || {};
      const lastRun = forgetting.last_run_at ? formatTimestamp(forgetting.last_run_at) : t("emotion.neverRun", "尚未执行");
      const stageBlock = (kind) => `
        <div>
          <h4 class="mini-label">${escapeHtml(t("emotion.stageDist", "{kind}阶段分布").replace("{kind}", kindLabel(kind)))}</h4>
          <div class="inline-actions" style="justify-content:flex-start;">${["0", "1", "2", "3"].map((stage) =>
            `<span class="mini-badge"><b>${escapeHtml(stageLabels[stage] || t("emotion.stageN", "阶段 {n}").replace("{n}", stage))}</b>&nbsp;${escapeHtml(fmt((distribution[kind] || {})[stage] || 0, 0))}</span>`).join("")}</div>
          <p class="trend-note">${escapeHtml(t("emotion.forgetMeta", "上次执行：{last} · 周期 {cycle} 天 · 宽限 {grace} 天")
            .replace("{last}", lastRun).replace("{cycle}", fmt(config.cycle_days || 0, 0)).replace("{grace}", fmt(config.grace_days || 0, 0)))}</p>
        </div>`;
      const stageTone = (stage) => Number(stage) >= 3 ? "warn" : Number(stage) === 2 ? "warn" : "";
      setHtml("emo-forget-body", `
        <div class="content-grid two-col">${stageBlock("expression")}${stageBlock("jargon")}</div>
        <div class="review-list">${candidates.map((item) => `
          <div class="table-row rich-row">
            <div>
              <strong>${escapeHtml(item.title || "--")}</strong>
              <small>${escapeHtml(kindLabel(item.kind))} · ${escapeHtml(item.group_id || "--")} · ${escapeHtml(t("emotion.lastUsed", "最后使用"))} ${escapeHtml(item.last_used ? formatTimestamp(item.last_used) : t("emotion.never", "从未"))}</small>
            </div>
            ${pill(stageLabels[String(item.stage)] || t("emotion.stageN", "阶段 {n}").replace("{n}", String(item.stage)), stageTone(item.stage))}
            <div class="row-actions compact-actions">
              ${button(t("emotion.reset", "重置"), `data-emo-action="reset_stage" data-kind="${escapeAttr(item.kind)}" data-id="${escapeAttr(item.id)}"`)}
              ${button(t("emotion.markDislike", "标记反感"), `data-emo-action="mark_dislike" data-kind="${escapeAttr(item.kind)}" data-id="${escapeAttr(item.id)}"`)}
              ${button(t("actions.delete", "删除"), `data-emo-action="delete_item" data-kind="${escapeAttr(item.kind)}" data-id="${escapeAttr(item.id)}"`, "danger-button")}
            </div>
          </div>`).join("") || empty(t("emotion.noCandidates", "暂无遗忘候选：所有条目都处于新鲜阶段。"))}</div>`);
    } else {
      setHtml("emo-forget-body", empty(t("emotion.forgetUnavailable", "遗忘管理器未运行：需要插件完整启动且数据库可用。")));
    }
  }

  function syncMoodFillButton() {
    const fill = $("emo-mood-fill");
    const group = $("emo-mood-group");
    const moods = (((state.emotion || {}).board || {}).moods || {}).active || [];
    if (fill) fill.hidden = !(moods.length && !(group && group.value.trim()));
    const submit = $("emo-mood-submit");
    if (submit) submit.disabled = !(group && group.value.trim());
  }

  function fillFirstMoodGroup() {
    const moods = (((state.emotion || {}).board || {}).moods || {}).active || [];
    const group = $("emo-mood-group");
    if (group && moods[0]) group.value = moods[0].group_id;
    syncMoodFillButton();
  }

  async function runEmotionAction(body, buttonEl) {
    if (buttonEl) { buttonEl.disabled = true; buttonEl.classList.add("is-busy"); }
    try {
      const result = await apiPost("emotion/action", body);
      showToast(result.message || t("messages.actionDone", "操作完成"), result.success === false ? "error" : "ok");
      await loadEmotion(true);
    } catch (error) {
      showToast(error.message || String(error), "error");
    } finally {
      if (buttonEl) { buttonEl.disabled = false; buttonEl.classList.remove("is-busy"); }
    }
  }

  async function submitEmotionMood(event) {
    const group = ($("emo-mood-group") || {}).value || "";
    if (!group.trim()) return;
    await runEmotionAction({
      action: "set_mood",
      group_id: group.trim(),
      mood_type: ($("emo-mood-type") || {}).value || "happy",
      intensity: Number(($("emo-mood-intensity") || {}).value) || 0.6,
      description: (($("emo-mood-desc") || {}).value || "").trim(),
    }, event && event.currentTarget);
  }

  async function handleEmotionAction(target) {
    await runEmotionAction({
      action: target.dataset.emoAction,
      kind: target.dataset.kind,
      id: Number(target.dataset.id),
    }, target);
  }

  function renderGenericBarChart(id, items) {
    const maxValue = Math.max(1, ...items.map((item) => Number(item.metric || 0)));
    setHtml(id, items.map((item) => {
      const value = Math.max(4, Math.min(100, Number(item.metric || 0) / maxValue * 100));
      return `<div class="bar-row" style="--accent:${escapeAttr(item.accent || "var(--chart-1)")}">
        <span>${escapeHtml(item.title)}</span>
        <div class="bar-track"><div class="bar-fill" style="--value:${value}"></div></div>
        <strong>${escapeHtml(fmt(item.metric, 0))}</strong>
      </div>`;
    }).join("") || empty());
  }

  function findReviewItem(kind, id) {
    const key = normalizeId(id);
    const pool = state.page === "persona-learning"
      ? listOf((state.pageData.persona || {}).pending).filter(isRecord)
      : reviewQueueItems(kind);
    return pool.find((item) => normalizeId(item.id) === key) || null;
  }

  async function reloadAfterReview() {
    if (state.page === "persona-learning") {
      clearCached("persona");
      await loadPersona(true);
    } else {
      clearCached("reviews");
      await loadReviews(true);
    }
    syncDashboardSnapshot();
  }

  // 单条审查：与独立版 ReviewCard 一致，通过 / 驳回 / 删除前均先确认
  async function handleReviewAction(kind, id, action) {
    const item = findReviewItem(kind, id) || { id };
    const actionText = action === "approve" ? t("actions.pass", "通过") : action === "reject" ? t("actions.rejectBack", "驳回") : t("actions.delete", "删除");
    const confirmLabel = action === "approve" ? t("actions.approve", "批准") : action === "reject" ? t("actions.rejectBack", "驳回") : t("actions.delete", "删除");
    const confirmed = await showConfirm(
      action === "delete" ? t("reviews.card.deleteTitle", "删除审查记录") : t("reviews.card.confirmTitle", "审查确认"),
      fill(t("reviews.card.confirmMessage", "确定{action}“{title}”吗？"), { action: actionText, title: reviewTitle(item) }),
      confirmLabel,
      action === "approve" ? "success" : "danger",
    );
    if (!confirmed) return;
    let payload;
    if (kind === "persona") {
      payload = action === "delete" ? { action: "delete", id } : { action: "review", id, decision: action };
    } else if (kind === "style") {
      payload = { action: `style_${action}`, id: normalizeId(id).replace(/^style_/, "") };
    } else {
      payload = { action: `jargon_${action}`, id };
    }
    try {
      const result = await apiPost("reviews/action", payload);
      if (!operationToast(result, t("messages.operationDone", "操作已完成"), t("messages.operationFailed", "操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("messages.operationFailed", "操作失败"), "error");
      return;
    }
    selectedReviewSet(kind).delete(normalizeId(id));
    await reloadAfterReview();
  }

  // 批量审查：未勾选时作用于当前列出的全部记录，勾选后只作用于选中项（双端同一语义与确认文案）
  async function handleBatchReviewAction(kind, action) {
    const selected = selectedReviewIds(kind);
    const scoped = selected.length > 0;
    const ids = (scoped ? selected : visibleReviewIds(kind))
      .map((id) => (kind === "style" ? normalizeId(id).replace(/^style_/, "") : normalizeId(id)))
      .filter(Boolean);
    if (!ids.length) {
      showToast(t("reviews.batch.empty", "当前没有可操作的记录"), "warn");
      return;
    }
    const actionText = action === "approve" ? t("actions.pass", "通过") : action === "reject" ? t("actions.rejectBack", "驳回") : t("actions.delete", "删除");
    const message = fill(scoped
      ? t("reviews.batch.confirmSelected", "确定对选中的 {count} 条{type}执行{action}吗？")
      : t("reviews.batch.confirmCurrent", "确定对当前 {count} 条{type}执行{action}吗？"), {
      count: ids.length,
      type: reviewQueueTitle(kind),
      action: actionText,
    });
    const confirmed = await showConfirm(t("modal.confirmBatch", "批量操作确认"), message, t("actions.confirm", "确认"), action === "approve" ? "success" : "danger");
    if (!confirmed) return;

    const payload = {
      action: action === "delete"
        ? kind === "persona" ? "batch_delete" : kind === "style" ? "batch_delete_style" : "batch_delete_jargon"
        : kind === "persona" ? "batch_review" : kind === "style" ? "batch_review_style" : "batch_review_jargon",
      ids,
      decision: action,
    };
    try {
      const result = await apiPost("reviews/action", payload);
      if (!operationToast(result, t("reviews.batch.done", "批量操作已完成"), t("messages.batchFailed", "批量操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("messages.batchFailed", "批量操作失败"), "error");
      return;
    }
    selectedReviewSet(kind).clear();
    await reloadAfterReview();
  }

  // 全局重新学习：自动选择消息最多的群组（无批次时也可用，与独立版同一确认与提示）
  async function handleRelearnAll(buttonEl) {
    const confirmed = await showConfirm(
      t("actions.relearn", "重新学习"),
      t("reviews.batches.relearnAllMessage", "将自动选择消息最多的群组重新学习，可能需要几分钟，确定继续吗？"),
      t("actions.confirm", "确认"),
      "warning",
    );
    if (!confirmed) return;
    if (buttonEl) { buttonEl.disabled = true; buttonEl.classList.add("is-busy"); }
    try {
      const result = await apiPost("batches/action", { action: "relearn_all" });
      if (!operationToast(result, t("messages.relearnSubmitted", "重新学习已提交"), t("reviews.batches.failed", "批次操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("reviews.batches.failed", "批次操作失败"), "error");
      return;
    } finally {
      if (buttonEl) { buttonEl.disabled = false; buttonEl.classList.remove("is-busy"); }
    }
    clearCached("batches");
    await loadReviewBatches(true);
  }

  // 最近学习批次：重跑学习 / 删除批次（与独立版同一确认与提示）
  async function handleBatchRecordAction(buttonEl) {
    const action = buttonEl.dataset.batchRecordAction;
    const id = action === "relearn" ? normalizeId(buttonEl.dataset.groupId) : normalizeId(buttonEl.dataset.id);
    if (!id) return;
    const confirmed = await showConfirm(
      action === "relearn" ? t("actions.relearn", "重新学习") : t("reviews.batches.deleteTitle", "删除学习批次"),
      action === "relearn" ? t("reviews.batches.relearnMessage", "重新学习可能需要几分钟，确定继续吗？") : t("messages.deleteIrreversible", "删除后不可撤销，确定继续吗？"),
      t("actions.confirm", "确认"),
      action === "delete" ? "danger" : "warning",
    );
    if (!confirmed) return;
    try {
      const result = await apiPost("batches/action", action === "relearn" ? { action, group_id: id } : { action, id });
      if (!operationToast(result, t("reviews.batches.done", "批次操作已完成"), t("reviews.batches.failed", "批次操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("reviews.batches.failed", "批次操作失败"), "error");
      return;
    }
    clearCached("batches");
    await loadReviewBatches(true);
  }

  async function handleJargonAction(action, id) {
    const key = normalizeId(id);
    const item = (state.jargon.items || []).find((entry) => normalizeId(entry.id) === key) || {};
    if (action === "edit") {
      state.jargon.editingId = key;
      state.jargon.draft = { content: String(item.content ?? item.jargon ?? ""), meaning: String(item.meaning ?? item.definition ?? "") };
      renderJargon(state.pageData.currentJargonData || {});
      $("jargon-edit-content")?.focus();
      return;
    }
    if (action === "cancel") {
      state.jargon.editingId = null;
      renderJargon(state.pageData.currentJargonData || {});
      return;
    }
    if (action === "save") {
      const draft = {
        content: $("jargon-edit-content")?.value ?? state.jargon.draft.content,
        meaning: $("jargon-edit-meaning")?.value ?? state.jargon.draft.meaning,
      };
      state.jargon.draft = draft;
      if (!draft.content.trim()) {
        showToast(t("jargon.termRequired", "词条不能为空"), "warn");
        return;
      }
      try {
        const result = await apiPost("jargon/action", { action: "update", id: key, content: draft.content, meaning: draft.meaning });
        if (!operationToast(result, t("jargon.saved", "词条已保存"), t("messages.saveFailed", "保存失败"))) return;
      } catch (error) {
        showToast(error.message || t("messages.saveFailed", "保存失败"), "error");
        return;
      }
      state.jargon.editingId = null;
      await reloadJargon();
      syncDashboardSnapshot();
      return;
    }
    if (action === "delete") {
      const confirmed = await showConfirm(
        t("jargon.deleteTitle", "删除黑话"),
        fill(t("jargon.deleteMessage", "确定删除“{term}”吗？"), { term: item.content ?? item.jargon ?? "" }),
        t("actions.confirm", "确认"),
        "danger",
      );
      if (!confirmed) return;
    }
    try {
      const result = await apiPost("jargon/action", { action, id: key });
      if (!operationToast(result, t("messages.operationDone", "操作已完成"), t("messages.operationFailed", "操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("messages.operationFailed", "操作失败"), "error");
      return;
    }
    state.selectedJargon.delete(key);
    await reloadJargon();
    syncDashboardSnapshot();
  }

  async function handleJargonBatchAction(action) {
    const visibleIds = jargonPageIds();
    if (action === "select_all") {
      visibleIds.forEach((id) => state.selectedJargon.add(id));
      renderJargon(state.pageData.currentJargonData || {});
      return;
    }
    if (action === "clear") {
      state.selectedJargon.clear();
      renderJargon(state.pageData.currentJargonData || {});
      return;
    }

    const ids = Array.from(state.selectedJargon).filter(Boolean);
    if (!ids.length) {
      showToast(t("jargon.selectFirst", "请先选择黑话条目"), "warn");
      return;
    }
    const actionText = action === "approve" ? t("actions.confirm", "确认") : action === "reject" ? t("actions.rejectBack", "驳回") : t("actions.delete", "删除");
    const confirmed = await showConfirm(
      t("modal.confirmBatch", "批量操作确认"),
      fill(t("jargon.confirmBatch", "确定批量{action}选中的 {count} 条黑话？"), { action: actionText, count: ids.length }),
      actionText,
      action === "approve" ? "success" : "danger",
    );
    if (!confirmed) return;

    try {
      const result = await apiPost("jargon/action", {
        action: action === "delete" ? "batch_delete" : "batch_review",
        ids,
        decision: action,
      });
      if (!operationToast(result, result.message || t("jargon.batchDone", "批量黑话操作完成"), t("messages.batchFailed", "批量操作失败"))) return;
    } catch (error) {
      showToast(error.message || t("messages.batchFailed", "批量操作失败"), "error");
      return;
    }
    state.selectedJargon.clear();
    await reloadJargon();
    syncDashboardSnapshot();
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

  // 审查队列风格卡「编辑」（双端并集：独立版同样提供编辑对话框）
  function handleStyleAction(action, id) {
    if (action !== "edit") return;
    const item = reviewQueueItems("style").find((entry) => normalizeId(entry.id) === normalizeId(id)) || {};
    const patternsSource = item.learned_patterns;
    const patterns = typeof patternsSource === "string" ? patternsSource : JSON.stringify(patternsSource || [], null, 2);
    showModal(t("modal.editStyle", "编辑表达方式"), `
      <label class="config-field"><span><strong>${escapeHtml(t("style.description", "描述"))}</strong></span><input id="modal-style-description" value="${escapeAttr(item.description ?? item.reason ?? "")}"></label>
      <label class="config-field"><span><strong>${escapeHtml(t("style.fewShots", "Few-shot 示例"))}</strong></span><textarea id="modal-style-few-shots" rows="7">${escapeHtml(item.few_shots_content ?? item.proposed_content ?? "")}</textarea></label>
      <label class="config-field"><span><strong>${escapeHtml(t("style.patternJson", "学习模式 JSON"))}</strong></span><textarea id="modal-style-patterns" rows="7">${escapeHtml(patterns)}</textarea></label>
      <button class="solid-button" type="button" id="modal-style-save" data-id="${escapeAttr(normalizeId(id).replace(/^style_/, ""))}">${escapeHtml(t("actions.save", "保存"))}</button>
    `);
  }

  function personaDetailHtml(detail) {
    const dialogs = listOf(detail.begin_dialogs);
    return `<p class="detail-line">${escapeHtml(fill(t("persona.detailMeta", "{name} · ID {id} · 示例对话 {dialogs} 条 · 工具 {tools} 个"), {
      name: personaNameOf(detail),
      id: textOrDash(personaIdOf(detail)),
      dialogs: dialogs.length,
      tools: listOf(detail.tools).length,
    }))}</p>
      <h4>${escapeHtml(t("persona.systemPrompt", "系统提示词"))}</h4>
      <pre class="code-preview">${escapeHtml(personaPromptOf(detail) || t("persona.emptyValue", "（空）"))}</pre>
      ${dialogs.length ? `<h4>${escapeHtml(t("persona.dialogsTitle", "示例对话"))}</h4><pre class="code-preview">${escapeHtml(summarize(detail.begin_dialogs))}</pre>` : ""}
      <details><summary>${escapeHtml(t("persona.rawPersona", "查看原始人格数据"))}</summary><pre class="code-preview">${escapeHtml(summarize(detail))}</pre></details>`;
  }

  function backupDetailHtml(detail) {
    const summary = isRecord(detail.summary) ? detail.summary : {};
    const personaSource = detail.original_persona ?? detail.persona_config;
    const persona = isRecord(personaSource) ? personaSource : {};
    const prompt = String(persona.prompt ?? persona.system_prompt ?? detail.persona_content ?? "");
    const dialogs = listOf(detail.imitation_dialogues);
    return `<p class="detail-line">${escapeHtml(fill(t("persona.backupDetail.meta", "{name} · 群组 {group} · {time}"), {
      name: textOrDash(summary.backup_name ?? detail.backup_name),
      group: textOrDash(summary.group_id ?? detail.group_id),
      time: formatTime(summary.timestamp ?? detail.timestamp),
    }))}</p>
      <p class="detail-line">${escapeHtml(fill(t("persona.backupDetail.reason", "备份原因：{reason}"), { reason: textOrDash(summary.reason ?? detail.reason ?? detail.backup_reason) }))}</p>
      <h4>${escapeHtml(t("persona.backupDetail.prompt", "人格提示词"))}</h4>
      <pre class="code-preview">${escapeHtml(prompt || t("persona.backupDetail.noPrompt", "（备份中没有提示词内容）"))}</pre>
      ${dialogs.length ? `<h4>${escapeHtml(fill(t("persona.backupDetail.dialogs", "示例对话（{count} 条）"), { count: dialogs.length }))}</h4><pre class="code-preview">${escapeHtml(summarize(dialogs))}</pre>` : ""}
      <details><summary>${escapeHtml(t("persona.backupDetail.raw", "查看原始备份数据"))}</summary><pre class="code-preview">${escapeHtml(summarize(detail))}</pre></details>`;
  }

  function showPersonaEditModal(personaId, item) {
    const beginDialogs = JSON.stringify(item.begin_dialogs || [], null, 2);
    showModal(t("modal.editPersona", "编辑人格"), `
      <label class="config-field"><span><strong>${escapeHtml(t("persona.id", "人格 ID"))}</strong></span><input id="modal-persona-id" value="${escapeAttr(personaId)}" disabled></label>
      <label class="config-field"><span><strong>${escapeHtml(t("persona.name", "名称"))}</strong></span><input id="modal-persona-name" value="${escapeAttr(item.name || personaId || "")}"></label>
      <label class="config-field"><span><strong>${escapeHtml(t("persona.systemPrompt", "系统提示词"))}</strong></span><textarea id="modal-persona-prompt" rows="9">${escapeHtml(item.system_prompt || item.prompt || "")}</textarea></label>
      <label class="config-field"><span><strong>${escapeHtml(t("persona.beginDialogsJson", "开场对话 JSON"))}</strong></span><textarea id="modal-persona-dialogs" rows="6">${escapeHtml(beginDialogs)}</textarea></label>
      <button class="solid-button" type="button" id="modal-persona-save" data-persona-id="${escapeAttr(personaId)}">${escapeHtml(t("actions.save", "保存"))}</button>
    `);
  }

  async function reloadPersona() {
    clearCached("persona");
    await loadPersona(true);
  }

  async function handlePersonaAction(buttonEl) {
    const action = buttonEl.dataset.personaAction;
    const personaId = normalizeId(buttonEl.dataset.personaId);
    const id = normalizeId(buttonEl.dataset.id);
    const groupId = buttonEl.dataset.groupId || "";
    const personaItem = (state.pageData.lastPersonaItems || []).find((entry) => personaIdOf(entry) === personaId) || {};

    if (action === "edit") {
      showPersonaEditModal(personaId, personaItem);
      return;
    }
    if (action === "view") {
      let detail = personaItem;
      if (personaId) {
        try {
          const result = await apiPost("persona/action", { action: "get", persona_id: personaId });
          if (result.success && isRecord(result.persona)) detail = result.persona;
          else showToast(result.message || t("persona.detailFailed", "人格详情加载失败"), "warn");
        } catch (error) {
          // 详情接口失败时回退到列表数据（列表本身已包含提示词内容）
          showToast(error.message || t("persona.detailFailed", "人格详情加载失败"), "warn");
        }
      }
      showModal(t("persona.detailTitle", "人格详情"), personaDetailHtml(detail));
      return;
    }
    if (action === "export") {
      if (!personaId) return;
      try {
        const result = await apiPost("persona/action", { action: "export", persona_id: personaId });
        if (!result.success || !isRecord(result.persona)) {
          showToast((!result.success && result.message) || t("persona.exportFailed", "人格导出失败"), "error");
          return;
        }
        downloadJson(`persona_${personaId}.json`, result.persona);
        showToast(t("persona.exported", "人格配置已导出"), "ok");
      } catch (error) {
        showToast(error.message || t("persona.exportFailed", "人格导出失败"), "error");
      }
      return;
    }
    if (action === "delete") {
      if (!personaId) return;
      const confirmed = await showConfirm(
        t("persona.deleteTitle", "删除人格"),
        fill(t("persona.deleteMessage", "确定删除人格“{name}”吗？此操作不可撤销。"), { name: personaNameOf(Object.keys(personaItem).length ? personaItem : { persona_id: personaId }) }),
        t("actions.delete", "删除"),
        "danger",
      );
      if (!confirmed) return;
      try {
        const result = await apiPost("persona/action", { action: "delete", persona_id: personaId });
        if (!operationToast(result, t("persona.deleted", "人格已删除"), t("messages.deleteFailed", "删除失败"))) return;
      } catch (error) {
        showToast(error.message || t("messages.deleteFailed", "删除失败"), "error");
        return;
      }
      await reloadPersona();
      return;
    }
    if (action === "backup_detail") {
      try {
        const result = await apiPost("persona/action", { action: "backup_detail", id, group_id: groupId });
        if (!result.success) {
          showToast(result.message || t("persona.backupDetailFailed", "备份详情加载失败"), "error");
          return;
        }
        showModal(t("modal.backupDetails", "备份详情"), backupDetailHtml(isRecord(result.backup) ? result.backup : {}));
      } catch (error) {
        showToast(error.message || t("persona.backupDetailFailed", "备份详情加载失败"), "error");
      }
      return;
    }
    if (action === "backup_restore" || action === "backup_delete") {
      const restore = action === "backup_restore";
      const confirmed = await showConfirm(
        restore ? t("persona.restoreTitle", "恢复人格备份") : t("persona.deleteBackupTitle", "删除人格备份"),
        restore ? t("persona.restoreMessage", "当前人格可能被覆盖，确定继续吗？") : t("persona.deleteBackupMessage", "此操作不可撤销，确定删除吗？"),
        t("actions.confirm", "确认"),
        "danger",
      );
      if (!confirmed) return;
      try {
        const result = await apiPost("persona/action", { action, id, group_id: groupId });
        if (!operationToast(result, t("messages.operationDone", "操作已完成"), t("persona.backupFailed", "备份操作失败"))) return;
      } catch (error) {
        showToast(error.message || t("persona.backupFailed", "备份操作失败"), "error");
        return;
      }
      await reloadPersona();
      syncDashboardSnapshot();
      return;
    }
    if (action === "reviewed_detail") {
      const item = (state.pageData.lastReviewedItems || []).find((entry) => normalizeId(entry.id) === id);
      if (!item) return;
      const before = reviewBeforePrompt(item);
      const after = reviewAfterPrompt(item);
      showModal(t("persona.reviewedDetailTitle", "已审查记录"), `
        <p class="detail-line">${escapeHtml(fill(t("persona.reviewedDetailMeta", "{status} · {time} · 备注：{comment}"), {
    status: reviewedStatusText(item),
    time: formatTime(item.review_time),
    comment: textOrDash(item.reviewer_comment),
  }))}</p>
        ${before || after ? `<h4>${escapeHtml(t("persona.before", "变更前"))}</h4><pre class="code-preview">${escapeHtml(before || t("persona.emptyValue", "（空）"))}</pre>
        <h4>${escapeHtml(t("persona.after", "变更后"))}</h4><pre class="code-preview">${escapeHtml(after || t("persona.emptyValue", "（空）"))}</pre>` : ""}
        <details><summary>${escapeHtml(t("reviews.card.raw", "查看原始审查数据"))}</summary><pre class="code-preview">${escapeHtml(summarize(item))}</pre></details>
      `);
      return;
    }
    if (action === "revert") {
      if (!id) return;
      const confirmed = await showConfirm(
        t("persona.revertTitle", "撤回审查决定"),
        t("persona.revertMessage", "撤回后该记录会重新回到待审队列；若记录已被他人处理，撤回会覆盖新的审查状态。确定继续吗？"),
        t("persona.revertConfirm", "确认撤回"),
        "warning",
      );
      if (!confirmed) return;
      try {
        const result = await apiPost("reviews/action", { action: "revert", id, reason: "WebUI 撤回" });
        if (!operationToast(result, t("persona.reverted", "已撤回审查决定"), t("persona.revertFailed", "撤回失败"))) return;
      } catch (error) {
        showToast(error.message || t("persona.revertFailed", "撤回失败"), "error");
        return;
      }
      clearCached("reviews");
      await reloadPersona();
      syncDashboardSnapshot();
    }
  }

  // 学习内容删除：与独立版一致先确认（删除后不可撤销）
  async function handleContentAction(buttonEl) {
    const id = normalizeId(buttonEl.dataset.id);
    if (!id) return;
    const confirmed = await showConfirm(t("content.deleteTitle", "删除学习内容"), t("messages.deleteIrreversible", "删除后不可撤销，确定继续吗？"), t("actions.confirm", "确认"), "danger");
    if (!confirmed) return;
    try {
      const result = await apiPost("content/action", { action: "delete_content", bucket: buttonEl.dataset.bucket, id });
      if (!operationToast(result, t("content.deleted", "学习内容已删除"), t("messages.deleteFailed", "删除失败"))) return;
    } catch (error) {
      showToast(error.message || t("messages.deleteFailed", "删除失败"), "error");
      return;
    }
    clearCached("content");
    clearCached("style");
    await loadContent(true);
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

  async function handlePageNav(buttonEl) {
    const next = Math.max(1, Number(buttonEl.dataset.pageTo) || 1);
    if (buttonEl.dataset.pageNav === "jargon") {
      state.jargon.page = next;
      state.jargon.editingId = null;
      await loadJargon(true);
    } else if (buttonEl.dataset.pageNav === "batches") {
      state.reviewBatchPage = next;
      await loadReviewBatches(true).catch((error) => showToast(error.message || t("reviews.batches.failed", "批次操作失败"), "error"));
    }
  }

  function bindEvents() {
    $("refresh-button")?.addEventListener("click", () => loadPageData(state.page, { force: true }));
    $("emo-mood-submit")?.addEventListener("click", submitEmotionMood);
    $("emo-mood-fill")?.addEventListener("click", fillFirstMoodGroup);
    $("emo-mood-group")?.addEventListener("input", syncMoodFillButton);
    $("emo-forget-run")?.addEventListener("click", (event) => runEmotionAction({ action: "run_forgetting_cycle" }, event.currentTarget));
    $("modal-close")?.addEventListener("click", closeModal);
    // 黑话词库：查询 / 状态 / 范围变化都回到第 1 页重新检索（与独立版一致）
    const searchJargon = () => {
      state.jargon.page = 1;
      state.jargon.editingId = null;
      reloadJargon();
    };
    $("jargon-search-button")?.addEventListener("click", searchJargon);
    $("jargon-confirmed")?.addEventListener("change", searchJargon);
    $("jargon-filter")?.addEventListener("change", searchJargon);
    $("jargon-list-refresh")?.addEventListener("click", () => reloadJargon());
    $("review-batch-relearn-all")?.addEventListener("click", (event) => handleRelearnAll(event.currentTarget));
    $("review-batch-refresh")?.addEventListener("click", () => {
      clearCached("batches");
      loadReviewBatches(true).catch((error) => showToast(error.message || t("reviews.batches.failed", "批次操作失败"), "error"));
    });
    $("persona-list-refresh")?.addEventListener("click", () => reloadPersona().catch((error) => showToast(error.message || String(error), "error")));
    $("content-search")?.addEventListener("input", (event) => {
      state.contentQuery = event.target.value || "";
      renderContent(state.pageData.content || {});
    });
    qsa("[data-review-search]").forEach((buttonEl) => {
      buttonEl.addEventListener("click", () => {
        clearCached("reviews");
        selectedReviewSet(buttonEl.dataset.reviewSearch || "").clear();
        loadPageData("reviews", { force: true });
      });
    });
    [
      "persona-review-keyword",
      "style-review-keyword",
      "jargon-review-keyword",
      "jargon-keyword",
    ].forEach((id) => {
      $(id)?.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        if (id === "jargon-keyword") {
          searchJargon();
        } else {
          qs(`[data-review-search="${id.split("-")[0]}"]`)?.click();
        }
      });
    });
    $("copy-insight-summary")?.addEventListener("click", async () => {
      const text = insightSummaryText(state.dashboard || {});
      const copied = () => showToast(t("messages.summaryCopied", "巡检摘要已复制"));
      try {
        await navigator.clipboard.writeText(text);
        copied();
        return;
      } catch (_) {}
      // iframe 可能未授予剪贴板权限：与独立版一样退回 execCommand；仍失败时展示原文便于手动复制
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.append(textarea);
      textarea.select();
      let done = false;
      try {
        done = document.execCommand("copy");
      } catch (_) {
        done = false;
      }
      textarea.remove();
      if (done) copied();
      else showModal(t("actions.copySummary", "复制摘要"), `<pre class="code-preview">${escapeHtml(text)}</pre>`);
    });
    $("graph-type")?.addEventListener("change", () => loadGraphs(true));
    $("config-save-button")?.addEventListener("click", async () => {
      const result = await apiPost("settings/action", { action: "save", config: collectConfigPayload() });
      const saved = !!result.success;
      showToast(
        result.message || (saved ? t("messages.settingsSaved", "配置已保存") : t("messages.settingsSaveFailed", "配置保存失败")),
        saved ? "ok" : "error",
      );
      if (!saved) return;
      state.dirtySettings.clear();
      state.pageData.settings = null;
      await loadPageData("settings", { force: true });
    });
    $("dependency-install-button")?.addEventListener("click", async () => {
      const installButton = $("dependency-install-button");
      const originalLabel = installButton?.textContent || t("actions.manualInstall", "手动安装");
      const settings = state.pageData.settings || {};
      const tier = $("dependency-tier")?.value || "full";
      const tierLabel = tier === "basic" ? t("settings.tierBasic", "基础") : t("settings.tierFull", "全能力");
      const confirmed = await showConfirm(
        t("settings.installConfirmTitle", "安装 Python 依赖"),
        t("settings.installConfirmBody", "即将调用 pip 安装{tier}依赖，确定继续吗？").replace("{tier}", tierLabel),
        t("actions.confirm", "确认"),
      );
      if (!confirmed) return;
      if (installButton) {
        installButton.disabled = true;
        installButton.classList.add("is-busy");
        installButton.textContent = t("actions.installing", "安装中");
      }
      setText("dependency-output", t("settings.installingDeps", "正在调用 pip 安装依赖，请等待命令输出..."));
      try {
        const result = await apiPost("settings/action", {
          action: "install_dependencies",
          manual_confirmed: true,
          source: settings.manual_dependency_source || "system_settings",
          tier,
          pip_mirror: $("pip-mirror-select")?.value || "default",
        });
        const detail = result.result || result;
        setText("dependency-output", detail.output || detail.message || result.message || t("settings.installDone", "依赖安装任务结束"));
        showToast(result.message || detail.message || t("settings.installDone", "依赖安装任务结束"), result.success !== false ? "ok" : "error");
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
    $("qchat-preview-button")?.addEventListener("click", () => runQchatImportAction("qchat_preview"));
    $("qchat-import-button")?.addEventListener("click", () => runQchatImportAction("qchat_import"));
    $("worldbook-preview-button")?.addEventListener("click", () => runWorldbookAction("worldbook_preview"));
    $("worldbook-import-button")?.addEventListener("click", () => runWorldbookAction("worldbook_import"));
    $("qchat-source-input")?.addEventListener("input", () => {
      state.qchatPreviewData = null;
      state.qchatShadowSender = "";
      renderQchatSenders();
    });

    // 切换聊天记录来源：与独立版一致重新读取状态并选中该来源的第一个群组
    qsa("#shadow-source button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (state.shadow.source === btn.dataset.shadowSource) return;
        state.shadow.source = btn.dataset.shadowSource || "live";
        clearCached("shadow-mode");
        await loadShadowMode(true, { resetGroup: true });
      });
    });
    $("shadow-group")?.addEventListener("change", async (event) => {
      const previousGroup = state.shadow.groupId;
      state.shadow.groupId = event.target.value || "";
      syncShadowTarget(previousGroup);
      await loadShadowCandidates(true);
    });
    $("shadow-learn-button")?.addEventListener("click", handleShadowLearn);
    document.addEventListener("click", (event) => {
      const candidate = event.target.closest("[data-shadow-candidate]");
      if (candidate) {
        state.shadow.selectedId = candidate.dataset.shadowCandidate || "";
        qsa("[data-shadow-candidate]").forEach((el) => {
          const selected = el.dataset.shadowCandidate === state.shadow.selectedId;
          el.classList.toggle("selected", selected);
          el.setAttribute("aria-pressed", String(selected));
        });
        refreshShadowLearnState();
        return;
      }
      const sender = event.target.closest("[data-qchat-sender]");
      if (sender) {
        const senderId = sender.dataset.qchatSender || "";
        state.qchatShadowSender = state.qchatShadowSender === senderId ? "" : senderId;
        renderQchatSenders();
      }
    });

    document.addEventListener("click", async (event) => {
      const target = event.target.closest("[data-route-card],[data-refresh-page],[data-review-action],[data-batch-review-kind],[data-batch-record-action],[data-page-nav],[data-jargon-action],[data-jargon-batch-action],[data-style-action],[data-style-bucket],[data-persona-action],[data-shadow-profile-action],[data-content-action],[data-settings-group],[data-emo-action]");
      if (!target) return;
      if (target.dataset.routeCard) {
        // 首页卡片 / 快捷坞为 <a href="#/page">：拦截默认跳转，避免 hashchange 重复加载
        if (target.tagName === "A") event.preventDefault();
        navigateToPage(target.dataset.routeCard);
      }
      if (target.dataset.refreshPage) loadPageData(target.dataset.refreshPage, { force: true });
      if (target.dataset.reviewAction) await handleReviewAction(target.dataset.kind, target.dataset.id, target.dataset.reviewAction);
      if (target.dataset.batchReviewKind) await handleBatchReviewAction(target.dataset.batchReviewKind, target.dataset.batchReviewAction || "approve");
      if (target.dataset.batchRecordAction) await handleBatchRecordAction(target);
      if (target.dataset.pageNav) await handlePageNav(target);
      if (target.dataset.jargonAction) await handleJargonAction(target.dataset.jargonAction, target.dataset.id);
      if (target.dataset.jargonBatchAction) await handleJargonBatchAction(target.dataset.jargonBatchAction);
      if (target.dataset.styleAction) handleStyleAction(target.dataset.styleAction, target.dataset.id);
      if (target.dataset.styleBucket) {
        state.styleBucket = target.dataset.styleBucket;
        renderStyleSamples();
      }
      if (target.dataset.personaAction) await handlePersonaAction(target);
      if (target.dataset.shadowProfileAction) await handleShadowProfileAction(target);
      if (target.dataset.contentAction) await handleContentAction(target);
      if (target.dataset.emoAction) await handleEmotionAction(target);
      if (target.dataset.settingsGroup) {
        state.settingsGroup = target.dataset.settingsGroup;
        renderSettings(state.pageData.settings || {});
      }
    });

    document.addEventListener("change", (event) => {
      const reviewSelect = event.target.closest("[data-review-select-kind]");
      if (reviewSelect) {
        const selection = selectedReviewSet(reviewSelect.dataset.reviewSelectKind);
        const id = normalizeId(reviewSelect.dataset.reviewSelectId);
        if (reviewSelect.checked) selection.add(id);
        else selection.delete(id);
        refreshSelectionLabels();
        return;
      }
      const jargonSelect = event.target.closest("[data-jargon-select-id]");
      if (jargonSelect) {
        const id = normalizeId(jargonSelect.dataset.jargonSelectId);
        if (jargonSelect.checked) state.selectedJargon.add(id);
        else state.selectedJargon.delete(id);
        refreshSelectionLabels();
        return;
      }
      const field = event.target.closest("[data-config-field]");
      if (!field) return;
      state.dirtySettings.set(field.dataset.configField, field.type === "checkbox" ? field.checked : field.value);
    });

    // 导入黑话面板：「导入黑话」切换、「收起」隐藏；导入后保留输入与导入报告（与独立版一致）
    document.addEventListener("click", async (event) => {
      if (event.target.closest("#jargon-import-toggle")) {
        const panel = $("jargon-import-panel");
        if (panel) panel.hidden = !panel.hidden;
        syncJargonImportButton();
        return;
      }
      if (event.target.closest("#jargon-import-collapse")) {
        const panel = $("jargon-import-panel");
        if (panel) panel.hidden = true;
        return;
      }
      const importSubmit = event.target.closest("#jargon-import-submit");
      if (importSubmit) await submitJargonImport(importSubmit);
    });

    document.addEventListener("input", (event) => {
      if (!event.target.closest) return;
      if (event.target.closest("#jargon-import-text")) {
        syncJargonImportButton();
        return;
      }
      const draftField = event.target.closest("[data-jargon-draft]");
      if (draftField && state.jargon.draft) state.jargon.draft[draftField.dataset.jargonDraft] = draftField.value;
    });

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("#modal-style-save");
      if (!save) return;
      try {
        const result = await apiPost("style/action", {
          action: "update",
          id: save.dataset.id,
          description: modalFieldValue("modal-style-description"),
          few_shots_content: modalFieldValue("modal-style-few-shots"),
          learned_patterns: parseModalJson("modal-style-patterns", []),
        });
        if (!operationToast(result, t("messages.styleUpdated", "表达方式已更新"), t("messages.saveFailed", "保存失败"))) return;
      } catch (error) {
        showToast(error.message || t("messages.saveFailed", "保存失败"), "error");
        return;
      }
      closeModal();
      clearCached("reviews");
      await loadReviews(true);
    });

    document.addEventListener("click", async (event) => {
      const save = event.target.closest("#modal-persona-save");
      if (!save) return;
      const personaId = save.dataset.personaId;
      try {
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
        if (!operationToast(result, t("messages.personaUpdated", "人格已更新"), t("messages.saveFailed", "保存失败"))) return;
      } catch (error) {
        showToast(error.message || t("messages.saveFailed", "保存失败"), "error");
        return;
      }
      closeModal();
      await reloadPersona();
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

  function setI18nFromBridge() {
    const rerender = () => {
      applyStaticI18n();
      const meta = PAGE_META[state.page] || PAGE_META.home;
      setText("page-kicker", t(meta[0], meta[2]));
      setText("page-title", t(meta[1], meta[3]));
      if (state.dashboard) renderDashboard(state.dashboard);
      const data = state.pageData[state.page] || state.pageData[state.page === "expression-learning" ? "style" : state.page];
      if (state.page === "reviews" && state.pageData.reviews) {
        renderReviews(state.pageData.reviews);
        if (state.pageData.reviewBatches) renderReviewBatches(state.pageData.reviewBatches);
      } else if (state.page === "jargon-learning" && state.pageData.currentJargonData) renderJargon(state.pageData.currentJargonData);
      else if (state.page === "expression-learning" && state.pageData.style) renderStyle(state.pageData.style);
      else if (state.page === "persona-learning" && state.pageData.persona) renderPersona(state.pageData.persona);
      else if (state.page === "shadow-mode" && state.pageData["shadow-mode"]) {
        renderShadowMode(state.pageData["shadow-mode"]);
        if (state.shadow.groupId) renderShadowCandidates(state.shadow.candidates || []);
      } else if (state.page === "content" && state.pageData.content) renderContent(state.pageData.content);
      else if (state.page === "graphs" && data) renderGraphs(data);
      else if (state.page === "integrations" && state.pageData.integrations) renderIntegrations(state.pageData.integrations);
      else if (state.page === "settings" && state.pageData.settings) renderSettings(state.pageData.settings);
    };
    try {
      const bridge = window.AstrBotPluginPage;
      if (bridge && bridge.onContextChange) bridge.onContextChange(rerender);
      if (bridge && bridge.onContext) bridge.onContext(rerender);
    } catch (_) {}
    rerender();
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
    ctx.strokeStyle = cssVar("--border-strong", "rgba(25, 25, 25, 0.42)");
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
      ctx.strokeStyle = cssVar("--border-strong", "rgba(25, 25, 25, 0.42)");
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
        ctx.fillStyle = cssVar("--signal-soft", "rgba(255, 250, 0, 0.2)");
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 10, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = node.source === "livingmemory" ? cssVar("--state", "#00ffa2") : cssVar(`--chart-${(index % 3) + 1}`, "#191919");
      ctx.beginPath();
      ctx.arc(node.x, node.y, isHovered ? radius + 2 : radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#191919";
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

  // ── 60s 静默刷新（对齐独立版 stores/dashboard 定时 refresh(true)）：只刷新快照驱动的页面，
  //    弹窗打开、设置有未保存修改、焦点在输入控件或页面不可见时跳过；不重绘任何表单 ──
  const AUTO_REFRESH_INTERVAL_MS = 60000;
  const SNAPSHOT_PAGES = new Set(["home", "overview", "insights", "monitoring"]);

  function autoRefreshBlocked() {
    if (!state.ready || state.dashboardLoading) return true;
    if (document.visibilityState === "hidden") return true;
    const modal = $("detail-modal");
    if (modal && (modal.open || modal.hasAttribute("open"))) return true;
    if (state.dirtySettings.size > 0) return true;
    const active = document.activeElement;
    return !!(active && typeof active.matches === "function"
      && active.matches("input, textarea, select, [contenteditable=\"true\"]"));
  }

  async function autoRefreshTick() {
    if (!SNAPSHOT_PAGES.has(state.page) || autoRefreshBlocked()) return;
    const data = await loadDashboard(true, { quiet: true });
    if (data && state.page === "overview") renderOverview(data);
  }

  function startAutoRefresh() {
    window.setInterval(() => {
      autoRefreshTick().catch(() => {});
    }, AUTO_REFRESH_INTERVAL_MS);
  }

  async function init() {
    setThemeFromBridge();
    bindEvents();
    initSpringMotion();
    // 首页静态结构（快捷坞 / 学习模块 / 入口卡骨架）先行渲染：桥接或快照失败时仍可导航
    state.dashboardLoading = SNAPSHOT_PAGES.has(resolvePageFromHash());
    renderHome({});
    try {
      await bridgeReady();
      setI18nFromBridge();
      state.runtimeStatusLabel = t("status.connected", "已连接");
      setText("runtime-status", state.runtimeStatusLabel);
      setText("runtime-summary", t("status.bridgeConnected", "已连接 AstrBot 插件页桥接层。"));
      navigateToPage(resolvePageFromHash(), { skipHash: true, force: true });
      startAutoRefresh();
    } catch (error) {
      state.dashboardLoading = false;
      renderHome({});
      showToast(error.message || String(error), "error");
      setText("runtime-status", t("status.bridgeFailed", "桥接失败"));
      setText("runtime-summary", error.message || String(error));
      setText("hero-status", t("status.bridgeFailed", "桥接失败"));
      setText("hero-summary", error.message || String(error));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
