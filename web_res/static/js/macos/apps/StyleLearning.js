/**
 * 对话风格学习 - Style Learning App
 * Displays style learning results with stat cards, 4 ECharts charts,
 * pattern lists, and learning content tabs.
 */
window.AppStyleLearning = {
  props: { app: Object },

  template: `
    <div class="app-content" ref="rootEl">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载数据中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>
        <!-- ========== 页面标题 ========== -->
        <div style="margin-bottom:16px;">
          <h2 style="margin:0 0 4px;font-size:18px;font-weight:600;color:#1d1d1f;">对话风格学习成果</h2>
          <p style="margin:0;font-size:12px;color:#86868b;">分析对话风格、情感模式、语言特征与话题偏好</p>
        </div>

        <!-- ========== 统计卡片 ========== -->
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-number">{{ styleResults.style_types_count || 0 }}</div>
            <div class="stat-label">学习风格类型</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatPercent(styleResults.avg_confidence) }}</div>
            <div class="stat-label">平均置信度</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(styleResults.total_samples) }}</div>
            <div class="stat-label">原始消息总数</div>
          </div>
          <div class="stat-card">
            <div class="stat-number" style="font-size:16px;">{{ formatTime(styleResults.latest_update) }}</div>
            <div class="stat-label">最近更新时间</div>
          </div>
        </div>

        <!-- ========== 时间范围选择器 ========== -->
        <div style="display:flex;justify-content:flex-end;margin-bottom:12px;">
          <div style="display:flex;gap:4px;background:#fff;border-radius:8px;padding:3px;border:1px solid #e5e5e5;">
            <span v-for="r in timeRanges" :key="r.value"
              @click="timeRange = r.value; refreshCharts()"
              :style="{
                padding: '4px 12px',
                fontSize: '11px',
                borderRadius: '6px',
                cursor: 'pointer',
                background: timeRange === r.value ? '#007aff' : 'transparent',
                color: timeRange === r.value ? '#fff' : '#86868b',
                fontWeight: timeRange === r.value ? '600' : '400',
                transition: 'all 0.2s'
              }">{{ r.label }}</span>
          </div>
        </div>

        <!-- ========== 图表网格 (2x2) ========== -->
        <div class="charts-grid">
          <!-- 1. 风格学习进度 - 水平条形图 -->
          <div class="chart-box">
            <h4>风格学习进度</h4>
            <div ref="styleProgressChart" class="chart-area"></div>
          </div>

          <!-- 2. 情感模式分析 - 雷达图 -->
          <div class="chart-box">
            <h4>情感模式分析</h4>
            <div ref="emotionPatternsChart" class="chart-area"></div>
          </div>

          <!-- 3. 语言风格分析 - 柱状图 -->
          <div class="chart-box">
            <h4>语言风格分析</h4>
            <div ref="languageStyleChart" class="chart-area"></div>
          </div>

          <!-- 4. 话题偏好 - 饼图 -->
          <div class="chart-box">
            <h4>话题偏好</h4>
            <div ref="topicPreferencesChart" class="chart-area"></div>
          </div>
        </div>

        <!-- ========== 发现的模式 ========== -->
        <div class="section-card">
          <h3><i class="material-icons" style="font-size:16px;vertical-align:-3px;margin-right:4px;">psychology</i>发现的模式</h3>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">

            <!-- 情感模式 -->
            <div style="flex:1;min-width:200px;">
              <h4 style="font-size:12px;font-weight:600;color:#1d1d1f;margin:0 0 8px;">情感模式</h4>
              <div v-if="patterns.emotion_patterns && patterns.emotion_patterns.length > 0">
                <div v-for="(item, idx) in patterns.emotion_patterns" :key="'ep'+idx"
                  style="padding:6px 10px;margin-bottom:4px;background:#f5f0ff;border-radius:6px;font-size:12px;color:#6750a4;">
                  <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:4px;">mood</i>
                  {{ typeof item === 'string' ? item : (item.name || item.pattern || JSON.stringify(item)) }}
                  <span v-if="item.score || item.confidence" style="float:right;color:#9c88c9;font-size:11px;">
                    {{ formatPercent(item.score || item.confidence) }}
                  </span>
                </div>
              </div>
              <div v-else style="font-size:12px;color:#86868b;padding:8px 0;">暂无数据</div>
            </div>

            <!-- 语言模式 -->
            <div style="flex:1;min-width:200px;">
              <h4 style="font-size:12px;font-weight:600;color:#1d1d1f;margin:0 0 8px;">语言模式</h4>
              <div v-if="patterns.language_patterns && patterns.language_patterns.length > 0">
                <div v-for="(item, idx) in patterns.language_patterns" :key="'lp'+idx"
                  style="padding:6px 10px;margin-bottom:4px;background:#e8f5e9;border-radius:6px;font-size:12px;color:#2e7d32;">
                  <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:4px;">translate</i>
                  {{ typeof item === 'string' ? item : (item.name || item.pattern || JSON.stringify(item)) }}
                  <span v-if="item.score || item.confidence" style="float:right;color:#66bb6a;font-size:11px;">
                    {{ formatPercent(item.score || item.confidence) }}
                  </span>
                </div>
              </div>
              <div v-else style="font-size:12px;color:#86868b;padding:8px 0;">暂无数据</div>
            </div>

            <!-- 话题模式 -->
            <div style="flex:1;min-width:200px;">
              <h4 style="font-size:12px;font-weight:600;color:#1d1d1f;margin:0 0 8px;">话题模式</h4>
              <div v-if="patterns.topic_patterns && patterns.topic_patterns.length > 0">
                <div v-for="(item, idx) in patterns.topic_patterns" :key="'tp'+idx"
                  style="padding:6px 10px;margin-bottom:4px;background:#fff3e0;border-radius:6px;font-size:12px;color:#e65100;">
                  <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:4px;">topic</i>
                  {{ typeof item === 'string' ? item : (item.name || item.pattern || JSON.stringify(item)) }}
                  <span v-if="item.score || item.confidence" style="float:right;color:#ffb74d;font-size:11px;">
                    {{ formatPercent(item.score || item.confidence) }}
                  </span>
                </div>
              </div>
              <div v-else style="font-size:12px;color:#86868b;padding:8px 0;">暂无数据</div>
            </div>

          </div>
        </div>

        <!-- ========== 学习内容 ========== -->
        <div class="section-card">
          <h3><i class="material-icons" style="font-size:16px;vertical-align:-3px;margin-right:4px;">library_books</i>学习内容</h3>

          <!-- 操作栏 -->
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
            <input id="contentSearchInput" type="text" v-model="contentSearch" placeholder="搜索内容..."
              style="flex:1;min-width:160px;padding:6px 12px;border:1px solid #e0e0e0;border-radius:6px;font-size:12px;outline:none;background:#fafafa;color:#333;" />
            <button @click="forceRefreshContent"
              style="padding:6px 14px;background:#007aff;color:#fff;border:none;border-radius:6px;font-size:12px;cursor:pointer;white-space:nowrap;">
              <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">refresh</i>强制刷新
            </button>
            <button @click="exportContent"
              style="padding:6px 14px;background:#34c759;color:#fff;border:none;border-radius:6px;font-size:12px;cursor:pointer;white-space:nowrap;">
              <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">download</i>导出
            </button>
          </div>

          <!-- Tab 栏 -->
          <div class="tab-bar">
            <div class="tab-item" :class="{ active: contentTab === 'dialogues' }" @click="contentTab = 'dialogues'">对话记录</div>
            <div class="tab-item" :class="{ active: contentTab === 'analysis' }" @click="contentTab = 'analysis'">分析结果</div>
            <div class="tab-item" :class="{ active: contentTab === 'features' }" @click="contentTab = 'features'">风格特征</div>
            <div class="tab-item" :class="{ active: contentTab === 'history' }" @click="contentTab = 'history'">学习历史</div>
          </div>

          <!-- 内容列表 -->
          <div style="max-height:400px;overflow-y:auto;">
            <div v-if="filteredContentList.length === 0" style="text-align:center;padding:30px 0;color:#86868b;font-size:12px;">
              <i class="material-icons" style="font-size:36px;display:block;margin-bottom:8px;opacity:0.4;">inbox</i>
              暂无数据
            </div>
            <div v-else>
              <div v-for="(item, idx) in filteredContentList" :key="contentTab + idx"
                style="padding:10px 12px;margin-bottom:6px;background:#fafafa;border-radius:8px;font-size:12px;line-height:1.6;color:#333;border:1px solid #f0f0f0;">
                <span v-html="highlightText(typeof item === 'string' ? item : (item.content || item.text || item.summary || JSON.stringify(item)))"></span>
              </div>
            </div>
          </div>
        </div>

        <!-- ========== 底部链接 ========== -->
        <div class="social-links">
          <a class="qq-link" href="https://qm.qq.com/q/1021544792" target="_blank" rel="noopener">QQ群: 1021544792</a>
          <a class="gh-link" href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" rel="noopener">GitHub</a>
        </div>
      </template>
    </div>
  `,

  data() {
    return {
      loading: true,
      styleResults: {},
      patterns: {},
      contentData: {},
      contentTab: "dialogues",
      contentSearch: "",
      timeRange: "30d",
      timeRanges: [
        { label: "7天", value: "7d" },
        { label: "30天", value: "30d" },
        { label: "90天", value: "90d" },
      ],
      chartInstances: {},
      resizeObserver: null,
      themeRegistered: false,
    };
  },

  computed: {
    /** Return the current tab's content list */
    currentContentList() {
      var tab = this.contentTab;
      if (!this.contentData) return [];
      if (tab === "dialogues") return this.contentData.dialogues || [];
      if (tab === "analysis") return this.contentData.analysis || [];
      if (tab === "features") return this.contentData.features || [];
      if (tab === "history") return this.contentData.history || [];
      return [];
    },

    /** Filter content by search keyword */
    filteredContentList() {
      var list = this.currentContentList;
      var keyword = (this.contentSearch || "").trim().toLowerCase();
      if (!keyword) return list;
      return list.filter(function (item) {
        var text =
          typeof item === "string"
            ? item
            : item.content || item.text || item.summary || JSON.stringify(item);
        return text.toLowerCase().indexOf(keyword) !== -1;
      });
    },
  },

  methods: {
    /* ---------- 工具函数 ---------- */
    formatNum(n) {
      if (n == null) return "0";
      n = Number(n);
      if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
      if (n >= 1000) return (n / 1000).toFixed(1) + "K";
      return String(n);
    },

    formatPercent(v) {
      if (v == null) return "0%";
      var num = Number(v);
      // If value is already 0-1 range, convert to percentage
      if (num > 0 && num <= 1) num = num * 100;
      return num.toFixed(1) + "%";
    },

    formatTime(ts) {
      if (!ts) return "暂无";
      try {
        var d;
        if (typeof ts === "number") {
          // Unix timestamp (seconds or milliseconds)
          d = new Date(ts > 1e12 ? ts : ts * 1000);
        } else {
          d = new Date(ts);
        }
        if (isNaN(d.getTime())) return String(ts);
        var month = String(d.getMonth() + 1).padStart(2, "0");
        var day = String(d.getDate()).padStart(2, "0");
        var hours = String(d.getHours()).padStart(2, "0");
        var minutes = String(d.getMinutes()).padStart(2, "0");
        return month + "-" + day + " " + hours + ":" + minutes;
      } catch (e) {
        return String(ts);
      }
    },

    highlightText(text) {
      var keyword = (this.contentSearch || "").trim();
      if (!keyword || !text) return this.escapeHtml(text || "");
      var escaped = this.escapeHtml(text);
      var escapedKeyword = this.escapeHtml(keyword);
      var regex = new RegExp(
        "(" + escapedKeyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")",
        "gi",
      );
      return escaped.replace(
        regex,
        '<mark style="background:#fff3cd;padding:0 2px;border-radius:2px;">$1</mark>',
      );
    },

    escapeHtml(str) {
      if (!str) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    },

    /* ---------- 注册 ECharts 主题 ---------- */
    registerTheme() {
      if (this.themeRegistered || window._materialThemeRegistered) {
        this.themeRegistered = true;
        return;
      }
      var echarts = window.echarts;
      if (!echarts) return;
      try {
        echarts.registerTheme("material", {
          color: [
            "#1976d2",
            "#4caf50",
            "#ff9800",
            "#f44336",
            "#9c27b0",
            "#00bcd4",
            "#795548",
            "#607d8b",
          ],
          backgroundColor: "transparent",
          textStyle: {
            fontFamily: "Roboto, sans-serif",
            fontSize: 12,
            color: "#424242",
          },
          title: {
            textStyle: {
              fontFamily: "Roboto, sans-serif",
              fontSize: 16,
              fontWeight: 500,
              color: "#212121",
            },
          },
          legend: {
            textStyle: {
              fontFamily: "Roboto, sans-serif",
              fontSize: 12,
              color: "#757575",
            },
          },
          categoryAxis: {
            axisLine: { lineStyle: { color: "#e0e0e0" } },
            axisTick: { lineStyle: { color: "#e0e0e0" } },
            axisLabel: { color: "#757575" },
            splitLine: { lineStyle: { color: "#f5f5f5" } },
          },
          valueAxis: {
            axisLine: { lineStyle: { color: "#e0e0e0" } },
            axisTick: { lineStyle: { color: "#e0e0e0" } },
            axisLabel: { color: "#757575" },
            splitLine: { lineStyle: { color: "#f5f5f5" } },
          },
          grid: { borderColor: "#e0e0e0" },
        });
        this.themeRegistered = true;
        window._materialThemeRegistered = true;
      } catch (e) {
        console.warn("[StyleLearning] registerTheme failed", e);
      }
    },

    /* ---------- 初始化单个 chart 实例 ---------- */
    initChart(refName) {
      var echarts = window.echarts;
      if (!echarts) return null;
      var dom = this.$refs[refName];
      if (!dom) return null;
      var existing = echarts.getInstanceByDom(dom);
      if (existing) {
        existing.dispose();
      }
      var chart = echarts.init(dom, "material");
      this.chartInstances[refName] = chart;
      return chart;
    },

    /* ---------- 空数据占位 ---------- */
    emptyOption(msg) {
      return {
        title: {
          text: msg || "暂无数据",
          left: "center",
          top: "middle",
          textStyle: { fontSize: 14, color: "#999" },
        },
        xAxis: { show: false },
        yAxis: { show: false },
        series: [],
      };
    },

    /* ---------- 数据获取 ---------- */
    async loadStyleData() {
      try {
        var resp = await fetch("/api/style_learning/results", {
          credentials: "include",
        });
        var data = await resp.json();
        // Normalize: backend returns { statistics: {...}, style_progress: [...] }
        // Flatten statistics into top-level for stat cards
        if (data && data.statistics) {
          data.style_types_count = data.statistics.unique_styles || 0;
          data.avg_confidence = data.statistics.avg_confidence || 0;
          data.total_samples = data.statistics.total_samples || 0;
          data.latest_update = data.statistics.latest_update || null;
        }
        this.styleResults = data || {};
      } catch (e) {
        console.error("[StyleLearning] loadStyleData error:", e);
        this.styleResults = {};
      }
    },

    async loadPatterns() {
      try {
        var resp = await fetch("/api/style_learning/patterns", {
          credentials: "include",
        });
        var data = await resp.json();
        // Normalize: backend returns topic_preferences, frontend expects topic_patterns
        if (data && data.topic_preferences && !data.topic_patterns) {
          data.topic_patterns = data.topic_preferences;
        }
        this.patterns = data || {};
      } catch (e) {
        console.error("[StyleLearning] loadPatterns error:", e);
        this.patterns = {};
      }
    },

    async loadContent(forceRefresh) {
      try {
        var url =
          "/api/style_learning/content_text?force_refresh=" +
          (forceRefresh ? "true" : "false");
        var resp = await fetch(url, { credentials: "include" });
        var data = await resp.json();
        this.contentData = data || {};
      } catch (e) {
        console.error("[StyleLearning] loadContent error:", e);
        this.contentData = {};
      }
    },

    async forceRefreshContent() {
      await this.loadContent(true);
    },

    /* ---------- 导出内容 ---------- */
    exportContent() {
      var lines = [];
      var self = this;
      var tabs = ["dialogues", "analysis", "features", "history"];
      var tabNames = {
        dialogues: "对话记录",
        analysis: "分析结果",
        features: "风格特征",
        history: "学习历史",
      };

      tabs.forEach(function (tab) {
        var list = self.contentData[tab] || [];
        if (list.length === 0) return;
        lines.push("===== " + tabNames[tab] + " =====");
        list.forEach(function (item, idx) {
          var text =
            typeof item === "string"
              ? item
              : item.content ||
                item.text ||
                item.summary ||
                JSON.stringify(item);
          lines.push(idx + 1 + ". " + text);
        });
        lines.push("");
      });

      if (lines.length === 0) {
        lines.push("暂无学习内容数据");
      }

      var blob = new Blob([lines.join("\n")], {
        type: "text/plain;charset=utf-8",
      });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download =
        "style_learning_content_" +
        new Date().toISOString().slice(0, 10) +
        ".txt";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },

    /* ---------- 刷新所有图表 ---------- */
    refreshCharts() {
      this.initStyleProgress();
      this.initEmotionPatterns();
      this.initLanguageStyle();
      this.initTopicPreferences();
    },

    /* ---------- 1. 风格学习进度 - 水平条形图 ---------- */
    initStyleProgress() {
      var chart =
        this.chartInstances["styleProgressChart"] ||
        this.initChart("styleProgressChart");
      if (!chart) return;

      var data = this.styleResults;
      if (
        !data.style_progress ||
        !Array.isArray(data.style_progress) ||
        data.style_progress.length === 0
      ) {
        chart.setOption(this.emptyOption("暂无风格学习数据"), true);
        return;
      }

      var styleProgress = data.style_progress;
      var labels = styleProgress.map(function (item) {
        if (item.group_id) return "群组" + item.group_id;
        if (item.timestamp)
          return new Date(item.timestamp * 1000).toLocaleDateString();
        return "未知";
      });
      var scores = styleProgress.map(function (item) {
        return Math.round((item.quality_score || 0) * 100);
      });
      var samples = styleProgress.map(function (item) {
        return (
          item.filtered_count || item.message_count || item.total_samples || 0
        );
      });

      chart.setOption(
        {
          tooltip: {
            trigger: "axis",
            axisPointer: { type: "shadow" },
            formatter: function (params) {
              var tip = params[0].name + "<br/>";
              params.forEach(function (p) {
                tip +=
                  p.marker +
                  " " +
                  p.seriesName +
                  ": " +
                  p.value +
                  (p.seriesIndex === 0 ? "%" : "") +
                  "<br/>";
              });
              return tip;
            },
          },
          legend: { data: ["质量分数(%)", "样本数量"] },
          grid: {
            left: "3%",
            right: "8%",
            bottom: "3%",
            top: "14%",
            containLabel: true,
          },
          xAxis: {
            type: "value",
            max: function (value) {
              return Math.max(100, value.max);
            },
          },
          yAxis: { type: "category", data: labels, inverse: true },
          series: [
            {
              name: "质量分数(%)",
              type: "bar",
              data: scores,
              itemStyle: {
                color: window.echarts
                  ? new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                      { offset: 0, color: "#667eea" },
                      { offset: 1, color: "#764ba2" },
                    ])
                  : "#667eea",
                borderRadius: [0, 4, 4, 0],
              },
              label: {
                show: true,
                position: "right",
                formatter: "{c}%",
                fontSize: 11,
              },
            },
            {
              name: "样本数量",
              type: "bar",
              data: samples,
              itemStyle: {
                color: window.echarts
                  ? new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                      { offset: 0, color: "#43e97b" },
                      { offset: 1, color: "#38f9d7" },
                    ])
                  : "#43e97b",
                borderRadius: [0, 4, 4, 0],
              },
              label: { show: true, position: "right", fontSize: 11 },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 2. 情感模式分析 - 雷达图 ---------- */
    initEmotionPatterns() {
      var chart =
        this.chartInstances["emotionPatternsChart"] ||
        this.initChart("emotionPatternsChart");
      if (!chart) return;

      var emotionPatterns = this.patterns.emotion_patterns || [];
      if (emotionPatterns.length === 0) {
        chart.setOption(this.emptyOption("暂无情感模式数据"), true);
        return;
      }

      // Build radar indicator and data from emotion patterns
      var indicators = [];
      var values = [];

      emotionPatterns.forEach(function (item) {
        var name =
          typeof item === "string" ? item : item.name || item.pattern || "未知";
        var value = 0;
        if (typeof item === "object" && item !== null) {
          value =
            item.score || item.confidence || item.value || item.weight || 0;
          if (value > 0 && value <= 1) value = value * 100;
        } else {
          value = 50; // Default for string-only patterns
        }
        indicators.push({ name: name, max: 100 });
        values.push(Math.round(value));
      });

      chart.setOption(
        {
          tooltip: {
            trigger: "item",
          },
          radar: {
            indicator: indicators,
            center: ["50%", "55%"],
            radius: "60%",
            shape: "polygon",
            splitArea: {
              areaStyle: {
                color: ["rgba(25,118,210,0.02)", "rgba(25,118,210,0.05)"],
              },
            },
            axisName: { color: "#757575", fontSize: 11 },
          },
          series: [
            {
              name: "情感模式",
              type: "radar",
              data: [
                {
                  value: values,
                  name: "情感维度",
                  symbol: "circle",
                  symbolSize: 6,
                  itemStyle: { color: "#9c27b0" },
                  lineStyle: { color: "#9c27b0", width: 2 },
                  areaStyle: { color: "rgba(156, 39, 176, 0.2)" },
                },
              ],
            },
          ],
        },
        true,
      );
    },

    /* ---------- 3. 语言风格分析 - 柱状图 ---------- */
    initLanguageStyle() {
      var chart =
        this.chartInstances["languageStyleChart"] ||
        this.initChart("languageStyleChart");
      if (!chart) return;

      var languagePatterns = this.patterns.language_patterns || [];
      if (languagePatterns.length === 0) {
        chart.setOption(this.emptyOption("暂无语言风格数据"), true);
        return;
      }

      var names = [];
      var values = [];

      languagePatterns.forEach(function (item) {
        var name =
          typeof item === "string" ? item : item.name || item.pattern || "未知";
        var value = 0;
        if (typeof item === "object" && item !== null) {
          value =
            item.score || item.confidence || item.value || item.count || 0;
          if (value > 0 && value <= 1) value = value * 100;
        } else {
          value = 50;
        }
        names.push(name);
        values.push(Math.round(value));
      });

      chart.setOption(
        {
          tooltip: {
            trigger: "axis",
            axisPointer: { type: "shadow" },
          },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "3%",
            top: "10%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: names,
            axisLabel: { rotate: names.length > 5 ? 30 : 0, fontSize: 11 },
          },
          yAxis: { type: "value", name: "特征值" },
          series: [
            {
              name: "语言特征",
              type: "bar",
              data: values,
              barMaxWidth: 40,
              itemStyle: {
                color: window.echarts
                  ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: "#4caf50" },
                      { offset: 1, color: "#81c784" },
                    ])
                  : "#4caf50",
                borderRadius: [4, 4, 0, 0],
              },
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: "rgba(0,0,0,0.3)",
                },
              },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 4. 话题偏好 - 饼图 ---------- */
    initTopicPreferences() {
      var chart =
        this.chartInstances["topicPreferencesChart"] ||
        this.initChart("topicPreferencesChart");
      if (!chart) return;

      var topicPatterns = this.patterns.topic_patterns || [];
      if (topicPatterns.length === 0) {
        chart.setOption(this.emptyOption("暂无话题偏好数据"), true);
        return;
      }

      var pieData = topicPatterns.map(function (item) {
        var name =
          typeof item === "string" ? item : item.name || item.pattern || "未知";
        var value = 0;
        if (typeof item === "object" && item !== null) {
          value =
            item.score || item.confidence || item.value || item.count || 1;
          if (value > 0 && value <= 1) value = Math.round(value * 100);
        } else {
          value = 1;
        }
        return { name: name, value: value };
      });

      chart.setOption(
        {
          tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
          legend: {
            bottom: "5%",
            left: "center",
            type: "scroll",
            textStyle: { fontSize: 11 },
          },
          series: [
            {
              name: "话题偏好",
              type: "pie",
              radius: ["35%", "65%"],
              center: ["50%", "45%"],
              data: pieData,
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: "rgba(0,0,0,0.5)",
                },
              },
              label: { show: true, formatter: "{b}: {d}%", fontSize: 11 },
              labelLine: { show: true },
              itemStyle: {
                borderRadius: 4,
                borderColor: "#fff",
                borderWidth: 2,
              },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 调整所有图表尺寸 ---------- */
    resizeAllCharts() {
      var self = this;
      Object.keys(this.chartInstances).forEach(function (key) {
        var c = self.chartInstances[key];
        if (c && !c.isDisposed()) {
          c.resize();
        }
      });
    },

    /* ---------- 销毁所有图表实例 ---------- */
    disposeAllCharts() {
      var self = this;
      Object.keys(this.chartInstances).forEach(function (key) {
        var c = self.chartInstances[key];
        if (c && !c.isDisposed()) {
          c.dispose();
        }
      });
      this.chartInstances = {};
    },
  },

  async mounted() {
    var self = this;

    // Register ECharts theme
    this.registerTheme();

    // Load all data in parallel
    await Promise.allSettled([
      this.loadStyleData(),
      this.loadPatterns(),
      this.loadContent(false),
    ]);

    this.loading = false;

    // Init charts after DOM renders
    this.$nextTick(function () {
      setTimeout(function () {
        self.initStyleProgress();
        self.initEmotionPatterns();
        self.initLanguageStyle();
        self.initTopicPreferences();

        // Set up ResizeObserver
        if (self.$refs.rootEl && typeof ResizeObserver !== "undefined") {
          self.resizeObserver = new ResizeObserver(function () {
            self.resizeAllCharts();
          });
          self.resizeObserver.observe(self.$refs.rootEl);
        }
      }, 100);
    });
  },

  beforeUnmount() {
    // Disconnect ResizeObserver
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    // Dispose all chart instances
    this.disposeAllCharts();
  },
};
