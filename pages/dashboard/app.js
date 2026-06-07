(() => {
  "use strict";

  const state = {
    data: null,
    activeTarget: "overview",
  };

  const els = {};
  const physics = {
    points: [],
    pointer: { x: 0, y: 0, active: false },
    running: false,
    last: 0,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function collectElements() {
    [
      "runtime-status",
      "runtime-summary",
      "full-dashboard-link",
      "refresh-button",
      "stat-messages",
      "stat-jargon",
      "stat-style",
      "stat-persona",
      "module-list",
      "module-chart",
      "intelligence-ring",
      "intelligence-score",
      "metrics-summary",
      "quick-entry-list",
      "detail-kicker",
      "detail-title",
      "error-panel",
    ].forEach((id) => {
      els[id] = $(id);
    });
  }

  function buildEndpoint(path) {
    return `page/${String(path).replace(/^\/+/, "").replace(/\/+/g, "/")}`;
  }

  async function apiGet(path, params) {
    const bridge = window.AstrBotPluginPage;
    if (!bridge) {
      throw new Error("AstrBot 插件页桥接 SDK 未加载");
    }
    await bridge.ready();
    return bridge.apiGet(buildEndpoint(path), params || {});
  }

  function unwrap(response) {
    if (response && response.status === "ok") {
      return response.data || {};
    }
    if (response && response.status === "error") {
      throw new Error(response.message || "请求失败");
    }
    return response || {};
  }

  function fmt(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return "0";
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(num);
  }

  function setText(id, value) {
    if (els[id]) {
      els[id].textContent = value;
    }
  }

  function setThemeFromBridge() {
    try {
      const bridge = window.AstrBotPluginPage;
      if (!bridge) return;
      const ctx = bridge.getContext && bridge.getContext();
      if (ctx && typeof ctx.isDark === "boolean") {
        document.documentElement.setAttribute("data-theme", ctx.isDark ? "dark" : "light");
      }
      if (bridge.onContext) {
        bridge.onContext((next) => {
          if (next && typeof next.isDark === "boolean") {
            document.documentElement.setAttribute("data-theme", next.isDark ? "dark" : "light");
          }
        });
      }
    } catch (_) {}
  }

  async function loadOverview() {
    setStatus("加载中", "正在同步插件运行状态", false);
    try {
      const data = unwrap(await apiGet("overview"));
      state.data = data;
      render(data);
    } catch (error) {
      setStatus("读取失败", error.message || String(error), true);
      renderErrors({ bridge: error.message || String(error) });
    }
  }

  function setStatus(label, summary, warn) {
    const pill = els["runtime-status"];
    if (pill) {
      pill.textContent = label;
      pill.classList.toggle("warn", !!warn);
    }
    setText("runtime-summary", summary);
  }

  function render(data) {
    const runtime = data.runtime || {};
    const webui = data.webui || {};
    const learning = data.learning_stats || {};
    const jargon = data.jargon || {};
    const styleStats = ((data.style || {}).statistics) || {};
    const persona = data.persona || {};

    if (els["full-dashboard-link"] && webui.dashboard_url) {
      els["full-dashboard-link"].href = webui.dashboard_url;
    }

    const degraded = runtime.database_degraded || Object.keys(data.errors || {}).length > 0;
    setStatus(
      degraded ? "部分可用" : "运行正常",
      degraded
        ? "嵌入式页面已载入，部分服务处于降级状态，可查看下方错误提示。"
        : `官方插件页已连接，完整 WebUI 入口为 ${webui.dashboard_url || "未配置"}。`,
      degraded,
    );

    setText("stat-messages", fmt(learning.total_messages_collected));
    setText("stat-jargon", fmt(jargon.confirmed_jargon));
    setText("stat-style", fmt(styleStats.unique_styles || styleStats.total_samples));
    setText("stat-persona", fmt(learning.persona_updates || persona.begin_dialog_count));

    renderModules(data.modules || []);
    renderCharts(data.modules || []);
    renderMetrics(data.metrics || {});
    renderQuickLinks(data.quick_links || []);
    renderErrors(data.errors || {});
    activateTarget(state.activeTarget);
  }

  function renderModules(modules) {
    if (!els["module-list"]) return;
    els["module-list"].innerHTML = modules.map((item) => `
      <article class="module-card" data-target="${escapeAttr(item.target)}" style="--accent:${escapeAttr(item.accent || "#2563eb")}">
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.description || "")}</p>
        <div class="module-card-footer">
          <div>
            <div class="module-metric">${escapeHtml(fmt(item.metric))}</div>
            <span class="stat-label">${escapeHtml(item.metric_label || "")}</span>
          </div>
          <span class="module-state">${item.enabled ? "启用" : "关闭"}</span>
        </div>
      </article>
    `).join("");

    els["module-list"].querySelectorAll(".module-card").forEach((card) => {
      card.addEventListener("click", () => activateTarget(card.dataset.target || "overview"));
    });
  }

  function renderCharts(modules) {
    if (!els["module-chart"]) return;
    const maxValue = Math.max(1, ...modules.map((item) => Number(item.metric || 0)));
    els["module-chart"].innerHTML = modules.map((item) => {
      const value = Math.max(4, Math.min(100, (Number(item.metric || 0) / maxValue) * 100));
      return `
        <div class="bar-row" style="--accent:${escapeAttr(item.accent || "#2563eb")}">
          <span>${escapeHtml(item.title)}</span>
          <div class="bar-track"><div class="bar-fill" style="--value:${value}"></div></div>
          <strong>${escapeHtml(fmt(item.metric))}</strong>
        </div>
      `;
    }).join("");
  }

  function renderMetrics(metrics) {
    const rawScore = Number(metrics.overall_score || 0);
    const normalized = rawScore <= 1 ? rawScore * 100 : rawScore;
    const score = Math.max(0, Math.min(100, normalized));
    if (els["intelligence-ring"]) {
      els["intelligence-ring"].style.setProperty("--value", String(score));
    }
    setText("intelligence-score", fmt(score));
    const dimensions = metrics.dimensions && typeof metrics.dimensions === "object"
      ? Object.keys(metrics.dimensions).length
      : 0;
    setText("metrics-summary", dimensions ? `已有 ${dimensions} 个维度参与评估。` : "智能指标服务暂未产生维度数据。");
  }

  function renderQuickLinks(links) {
    if (!els["quick-entry-list"]) return;
    els["quick-entry-list"].innerHTML = links.map((link) => `
      <a class="quick-entry" href="${escapeAttr(link.url || "#")}" target="${String(link.url || "").startsWith("http") ? "_blank" : "_self"}" rel="noreferrer">
        <span>
          ${escapeHtml(link.label || "入口")}
          <small>${escapeHtml(link.description || "")}</small>
        </span>
        <strong>›</strong>
      </a>
    `).join("");
  }

  function renderErrors(errors) {
    if (!els["error-panel"]) return;
    const entries = Object.entries(errors || {});
    els["error-panel"].hidden = entries.length === 0;
    els["error-panel"].innerHTML = entries.map(([key, value]) => `<p><strong>${escapeHtml(key)}</strong>: ${escapeHtml(value)}</p>`).join("");
  }

  function activateTarget(target) {
    state.activeTarget = target || "overview";
    document.querySelectorAll(".module-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.target === state.activeTarget);
    });
    document.querySelectorAll(".module-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.target === state.activeTarget);
    });

    const module = (state.data && (state.data.modules || []).find((item) => item.target === state.activeTarget)) || null;
    setText("detail-kicker", state.activeTarget === "overview" ? "Overview" : state.activeTarget);
    setText("detail-title", module ? module.title : "模块状态");
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

  function bindEvents() {
    if (els["refresh-button"]) {
      els["refresh-button"].addEventListener("click", loadOverview);
    }
    document.querySelectorAll(".module-tab").forEach((tab) => {
      tab.addEventListener("click", () => activateTarget(tab.dataset.target || "overview"));
    });
    initSpringMotion();
  }

  function initSpringMotion() {
    const stage = document.querySelector(".spring-stage");
    if (!stage) return;

    physics.points = Array.from(stage.querySelectorAll(".spring-node:not(.node-core)")).map((el, index) => ({
      el,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      seed: index * 2.1,
    }));
    if (!physics.points.length) return;

    stage.addEventListener("pointermove", (event) => {
      const rect = stage.getBoundingClientRect();
      physics.pointer.x = event.clientX - rect.left;
      physics.pointer.y = event.clientY - rect.top;
      physics.pointer.active = true;
    });
    stage.addEventListener("pointerleave", () => {
      physics.pointer.active = false;
    });

    if (!physics.running) {
      physics.running = true;
      physics.last = performance.now();
      requestAnimationFrame(tickSpringMotion);
    }
  }

  function tickSpringMotion(now) {
    if (!physics.running) return;
    const dt = Math.min(0.033, Math.max(0.001, (now - physics.last) / 1000));
    physics.last = now;

    physics.points.forEach((point) => {
      const rect = point.el.parentElement.getBoundingClientRect();
      const own = point.el.getBoundingClientRect();
      const breatheX = Math.sin(now / 1200 + point.seed) * 14;
      const breatheY = Math.cos(now / 1350 + point.seed) * 12;
      let targetX = breatheX;
      let targetY = breatheY;

      if (physics.pointer.active) {
        const cx = own.left - rect.left + own.width / 2 + point.x;
        const cy = own.top - rect.top + own.height / 2 + point.y;
        const dx = cx - physics.pointer.x;
        const dy = cy - physics.pointer.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const force = Math.max(0, 110 - dist) / 110;
        targetX += (dx / dist) * force * 46;
        targetY += (dy / dist) * force * 46;
      }

      const spring = 46;
      const damping = 12;
      point.vx += (targetX - point.x) * spring * dt;
      point.vy += (targetY - point.y) * spring * dt;
      point.vx *= Math.max(0, 1 - damping * dt);
      point.vy *= Math.max(0, 1 - damping * dt);
      point.x += point.vx * dt * 60;
      point.y += point.vy * dt * 60;

      const scale = 1 + Math.min(0.12, Math.hypot(point.vx, point.vy) / 900);
      point.el.style.transform = `translate3d(${point.x.toFixed(2)}px, ${point.y.toFixed(2)}px, 0) scale(${scale.toFixed(3)})`;
    });

    requestAnimationFrame(tickSpringMotion);
  }

  async function init() {
    collectElements();
    setThemeFromBridge();
    bindEvents();
    await loadOverview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
