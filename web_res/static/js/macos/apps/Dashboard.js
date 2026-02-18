/**
 * 可视化大屏 - Dashboard App
 * 包含 4 个统计卡片和 7 个 ECharts 图表
 * 自动每 5 秒刷新数据
 */
window.AppDashboard = {
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
        <!-- ========== 统计卡片 ========== -->
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(metrics.total_messages_collected) }}</div>
            <div class="stat-label">总消息数</div>
            <div class="stat-trend" :class="trends.message_growth >= 0 ? 'positive' : 'negative'">
              {{ trends.message_growth >= 0 ? '+' : '' }}{{ trends.message_growth }}%
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(metrics.filtered_messages) }}</div>
            <div class="stat-label">筛选消息数</div>
            <div class="stat-trend" :class="trends.filtered_growth >= 0 ? 'positive' : 'negative'">
              {{ trends.filtered_growth >= 0 ? '+' : '' }}{{ trends.filtered_growth }}%
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(totalLLMCalls) }}</div>
            <div class="stat-label">LLM调用次数</div>
            <div class="stat-trend" :class="trends.llm_growth >= 0 ? 'positive' : 'negative'">
              {{ trends.llm_growth >= 0 ? '+' : '' }}{{ trends.llm_growth }}%
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(metrics.learning_sessions ? metrics.learning_sessions.active_sessions : 0) }}</div>
            <div class="stat-label">学习会话数</div>
            <div class="stat-trend" :class="trends.sessions_growth >= 0 ? 'positive' : 'negative'">
              {{ trends.sessions_growth >= 0 ? '+' : '' }}{{ trends.sessions_growth }}%
            </div>
          </div>
        </div>

        <!-- ========== 图表网格 ========== -->
        <div class="charts-grid">

          <!-- 1. LLM 模型调用分布 - 饼图 -->
          <div class="chart-box">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <h4 style="margin:0;">LLM模型调用分布</h4>
              <select v-model="pieRange" @change="updateLLMPie" style="font-size:11px;padding:2px 6px;border:1px solid #e0e0e0;border-radius:4px;background:#fff;color:#333;cursor:pointer;">
                <option value="1h">1h</option>
                <option value="24h">24h</option>
                <option value="7d">7d</option>
                <option value="30d">30d</option>
              </select>
            </div>
            <div ref="llmPieChart" class="chart-area"></div>
          </div>

          <!-- 2. 消息处理趋势 - 折线图 -->
          <div class="chart-box">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <h4 style="margin:0;">消息处理趋势</h4>
              <select v-model="trendRange" @change="updateMessageTrend" style="font-size:11px;padding:2px 6px;border:1px solid #e0e0e0;border-radius:4px;background:#fff;color:#333;cursor:pointer;">
                <option value="1h">1h</option>
                <option value="24h">24h</option>
                <option value="7d">7d</option>
                <option value="30d">30d</option>
              </select>
            </div>
            <div ref="messageTrendChart" class="chart-area"></div>
          </div>

          <!-- 3. LLM 响应时间分析 - 柱状图 -->
          <div class="chart-box">
            <h4>LLM响应时间分析</h4>
            <div ref="responseTimeChart" class="chart-area"></div>
          </div>

          <!-- 4. 学习进度概览 - 仪表盘 -->
          <div class="chart-box">
            <h4>学习进度概览</h4>
            <div ref="learningGaugeChart" class="chart-area"></div>
          </div>

          <!-- 5. 系统状态监控 - 雷达图 -->
          <div class="chart-box">
            <h4>系统状态监控</h4>
            <div ref="systemRadarChart" class="chart-area"></div>
          </div>

          <!-- 6. 对话风格学习进度 - 混合柱线图 -->
          <div class="chart-box">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <h4 style="margin:0;">对话风格学习进度</h4>
              <select v-model="styleRange" @change="updateStyleChart" style="font-size:11px;padding:2px 6px;border:1px solid #e0e0e0;border-radius:4px;background:#fff;color:#333;cursor:pointer;">
                <option value="1h">1h</option>
                <option value="24h">24h</option>
                <option value="7d">7d</option>
                <option value="30d">30d</option>
              </select>
            </div>
            <div ref="styleChart" class="chart-area"></div>
          </div>

          <!-- 7. 用户活跃度热力图 - 宽度全跨 -->
          <div class="chart-box" style="grid-column:1/-1;">
            <h4>用户活跃度热力图</h4>
            <div ref="heatmapChart" class="chart-area"></div>
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
      metrics: {},
      trends: {
        message_growth: 0,
        filtered_growth: 0,
        llm_growth: 0,
        sessions_growth: 0,
      },
      analyticsData: {},
      styleData: {},
      pieRange: "24h",
      trendRange: "24h",
      styleRange: "24h",
      chartInstances: {},
      refreshTimer: null,
      resizeObserver: null,
      themeRegistered: false,
    };
  },

  computed: {
    totalLLMCalls() {
      const calls = this.metrics.llm_calls || {};
      return Object.values(calls).reduce(function (sum, m) {
        return sum + (m.total_calls || 0);
      }, 0);
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

    /* ---------- 注册 ECharts 主题 ---------- */
    registerTheme() {
      if (this.themeRegistered) return;
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
      } catch (e) {
        console.warn("[Dashboard] registerTheme failed", e);
      }
    },

    /* ---------- 初始化单个 chart 实例 ---------- */
    initChart(refName) {
      var echarts = window.echarts;
      if (!echarts) return null;
      var dom = this.$refs[refName];
      if (!dom) return null;
      // 销毁可能遗留的实例
      var existing = echarts.getInstanceByDom(dom);
      if (existing) {
        existing.dispose();
      }
      var chart = echarts.init(dom, "material");
      this.chartInstances[refName] = chart;
      return chart;
    },

    /* ---------- 数据获取 ---------- */
    async fetchAllData() {
      try {
        var results = await Promise.allSettled([
          fetch("/api/metrics").then(function (r) {
            return r.json();
          }),
          fetch("/api/metrics/trends").then(function (r) {
            return r.json();
          }),
          fetch("/api/analytics/trends").then(function (r) {
            return r.json();
          }),
          fetch("/api/style_learning/results").then(function (r) {
            return r.json();
          }),
        ]);

        if (results[0].status === "fulfilled")
          this.metrics = results[0].value || {};
        if (results[1].status === "fulfilled") {
          var t = results[1].value || {};
          this.trends = {
            message_growth: t.message_growth || 0,
            filtered_growth: t.filtered_growth || 0,
            llm_growth: t.llm_growth || 0,
            sessions_growth: t.sessions_growth || 0,
          };
        }
        if (results[2].status === "fulfilled")
          this.analyticsData = results[2].value || {};
        if (results[3].status === "fulfilled")
          this.styleData = results[3].value || {};
      } catch (e) {
        console.error("[Dashboard] fetchAllData error:", e);
      }
    },

    /* ---------- 刷新所有图表 ---------- */
    async refreshAll() {
      await this.fetchAllData();
      this.updateLLMPie();
      this.updateMessageTrend();
      this.updateResponseTime();
      this.updateLearningGauge();
      this.updateSystemRadar();
      this.updateStyleChart();
      this.updateHeatmap();
    },

    /* ---------- 1. LLM 模型调用分布 - 饼图 ---------- */
    updateLLMPie() {
      var chart =
        this.chartInstances["llmPieChart"] || this.initChart("llmPieChart");
      if (!chart) return;

      var llmData = this.metrics.llm_calls || {};
      var data = Object.entries(llmData).map(function (entry) {
        return { name: entry[0], value: entry[1].total_calls || 0 };
      });

      if (data.length === 0) {
        chart.setOption(this.emptyOption("暂无LLM调用数据"), true);
        return;
      }

      chart.setOption(
        {
          tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
          legend: { bottom: "5%", left: "center" },
          series: [
            {
              name: "LLM调用分布",
              type: "pie",
              radius: ["40%", "70%"],
              center: ["50%", "45%"],
              data: data,
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: "rgba(0,0,0,0.5)",
                },
              },
              label: { show: true, formatter: "{b}: {c}" },
              labelLine: { show: true },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 2. 消息处理趋势 - 折线图 ---------- */
    updateMessageTrend() {
      var chart =
        this.chartInstances["messageTrendChart"] ||
        this.initChart("messageTrendChart");
      if (!chart) return;

      var hourlyData = this.analyticsData.hourly_trends || [];
      var hours, rawMessages, filteredMessages;

      if (hourlyData.length > 0) {
        hours = hourlyData.map(function (i) {
          return i.time;
        });
        rawMessages = hourlyData.map(function (i) {
          return i.raw_messages;
        });
        filteredMessages = hourlyData.map(function (i) {
          return i.filtered_messages;
        });
      } else {
        // 生成空的 24 小时时间轴
        hours = [];
        for (var i = 23; i >= 0; i--) {
          var d = new Date(Date.now() - i * 3600000);
          hours.push(d.getHours() + ":00");
        }
        rawMessages = new Array(24).fill(0);
        filteredMessages = new Array(24).fill(0);
      }

      chart.setOption(
        {
          tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
          legend: { data: ["原始消息", "筛选消息"] },
          grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
          xAxis: { type: "category", data: hours, boundaryGap: false },
          yAxis: { type: "value" },
          series: [
            {
              name: "原始消息",
              type: "line",
              data: rawMessages,
              smooth: true,
              itemStyle: { color: "#2196f3" },
              areaStyle: { opacity: 0.3 },
            },
            {
              name: "筛选消息",
              type: "line",
              data: filteredMessages,
              smooth: true,
              itemStyle: { color: "#4caf50" },
              areaStyle: { opacity: 0.3 },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 3. LLM 响应时间分析 - 柱状图 ---------- */
    updateResponseTime() {
      var echarts = window.echarts;
      var chart =
        this.chartInstances["responseTimeChart"] ||
        this.initChart("responseTimeChart");
      if (!chart) return;

      var llmData = this.metrics.llm_calls || {};
      var models = Object.keys(llmData);
      var times = Object.values(llmData).map(function (s) {
        return s.avg_response_time_ms || 0;
      });

      if (models.length === 0) {
        chart.setOption(this.emptyOption("暂无LLM响应数据"), true);
        return;
      }

      var barColor = echarts
        ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "#1976d2" },
            { offset: 1, color: "#64b5f6" },
          ])
        : "#1976d2";

      chart.setOption(
        {
          tooltip: { trigger: "axis", formatter: "{b}<br/>{a}: {c}ms" },
          grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
          xAxis: { type: "category", data: models, axisLabel: { rotate: 45 } },
          yAxis: { type: "value", name: "响应时间(ms)" },
          series: [
            {
              name: "平均响应时间",
              type: "bar",
              data: times,
              itemStyle: { color: barColor },
              markLine: { data: [{ type: "average", name: "平均值" }] },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 4. 学习进度概览 - 仪表盘 ---------- */
    updateLearningGauge() {
      var chart =
        this.chartInstances["learningGaugeChart"] ||
        this.initChart("learningGaugeChart");
      if (!chart) return;

      var efficiency = 0;
      if (this.metrics.learning_efficiency !== undefined) {
        efficiency = this.metrics.learning_efficiency;
      } else {
        var total = this.metrics.total_messages_collected || 0;
        var filtered = this.metrics.filtered_messages || 0;
        efficiency = total > 0 ? (filtered / total) * 100 : 0;
      }

      chart.setOption(
        {
          series: [
            {
              type: "gauge",
              startAngle: 180,
              endAngle: 0,
              center: ["50%", "75%"],
              radius: "90%",
              min: 0,
              max: 100,
              splitNumber: 8,
              axisLine: {
                lineStyle: {
                  width: 6,
                  color: [
                    [0.25, "#ff4444"],
                    [0.5, "#ff9800"],
                    [0.75, "#4caf50"],
                    [1, "#1976d2"],
                  ],
                },
              },
              pointer: {
                icon: "path://M12.8,0.7l12,40.1H0.7L12.8,0.7z",
                length: "12%",
                width: 20,
                offsetCenter: [0, "-60%"],
                itemStyle: { color: "auto" },
              },
              axisTick: { length: 12, lineStyle: { color: "auto", width: 2 } },
              splitLine: { length: 20, lineStyle: { color: "auto", width: 5 } },
              axisLabel: {
                color: "#464646",
                fontSize: 10,
                distance: -60,
                formatter: function (value) {
                  if (value === 100) return "优秀";
                  if (value === 75) return "良好";
                  if (value === 50) return "一般";
                  if (value === 25) return "较差";
                  return "";
                },
              },
              title: { offsetCenter: [0, "-10%"], fontSize: 16 },
              detail: {
                fontSize: 30,
                offsetCenter: [0, "-35%"],
                valueAnimation: true,
                formatter: function (v) {
                  return Math.round(v) + "%";
                },
                color: "auto",
              },
              data: [{ value: efficiency.toFixed(1), name: "学习效率" }],
            },
          ],
        },
        true,
      );
    },

    /* ---------- 5. 系统状态监控 - 雷达图 ---------- */
    updateSystemRadar() {
      var chart =
        this.chartInstances["systemRadarChart"] ||
        this.initChart("systemRadarChart");
      if (!chart) return;

      var stats = this.metrics;
      var totalMessages = stats.total_messages_collected || 0;
      var filteredMessages = stats.filtered_messages || 0;

      // 消息抓取效率
      var messageCapture =
        totalMessages > 0 ? Math.min(100, (totalMessages / 1000) * 100) : 0;
      // 数据筛选质量
      var filteringQuality =
        totalMessages > 0 ? (filteredMessages / totalMessages) * 100 : 0;
      // LLM 调用健康度
      var llmModels = Object.values(stats.llm_calls || {});
      var avgSuccessRate =
        llmModels.length > 0
          ? (llmModels.reduce(function (s, m) {
              return s + (m.success_rate || 0);
            }, 0) /
              llmModels.length) *
            100
          : 0;
      // 学习质量
      var learningQuality = stats.learning_efficiency || 0;
      // 响应速度
      var avgResponseTime =
        llmModels.length > 0
          ? llmModels.reduce(function (s, m) {
              return s + (m.avg_response_time_ms || 0);
            }, 0) / llmModels.length
          : 2000;
      var responseSpeed = Math.max(0, 100 - avgResponseTime / 20);
      // 系统稳定性
      var sm = stats.system_metrics || {};
      var systemStability =
        (Math.max(0, 100 - (sm.cpu_percent || 0)) +
          Math.max(0, 100 - (sm.memory_percent || 0))) /
        2;

      chart.setOption(
        {
          tooltip: { formatter: "{b}: {c}%" },
          radar: {
            indicator: [
              { name: "消息抓取", max: 100 },
              { name: "数据筛选", max: 100 },
              { name: "LLM调用", max: 100 },
              { name: "学习质量", max: 100 },
              { name: "响应速度", max: 100 },
              { name: "系统稳定性", max: 100 },
            ],
            center: ["50%", "50%"],
            radius: "65%",
          },
          series: [
            {
              name: "系统状态",
              type: "radar",
              data: [
                {
                  value: [
                    Math.round(messageCapture),
                    Math.round(filteringQuality),
                    Math.round(avgSuccessRate),
                    Math.round(learningQuality),
                    Math.round(responseSpeed),
                    Math.round(systemStability),
                  ],
                  name: "当前状态",
                  itemStyle: { color: "#1976d2" },
                  areaStyle: { opacity: 0.3 },
                },
              ],
            },
          ],
        },
        true,
      );
    },

    /* ---------- 6. 对话风格学习进度 - 混合柱线图 ---------- */
    updateStyleChart() {
      var echarts = window.echarts;
      var chart =
        this.chartInstances["styleChart"] || this.initChart("styleChart");
      if (!chart) return;

      var data = this.styleData;
      if (
        data.error ||
        !data.style_progress ||
        !Array.isArray(data.style_progress) ||
        data.style_progress.length === 0
      ) {
        chart.setOption(
          this.emptyOption(data.error || "暂无风格学习数据"),
          true,
        );
        return;
      }

      var styleProgress = data.style_progress;
      var labels = styleProgress.map(function (item) {
        if (item.group_id) return "\u7FA4\u7EC4" + item.group_id;
        if (item.timestamp)
          return new Date(item.timestamp * 1000).toLocaleDateString();
        return "\u672A\u77E5";
      });
      var confidenceData = styleProgress.map(function (item) {
        return (item.quality_score || 0) * 100;
      });
      var sampleData = styleProgress.map(function (item) {
        return item.filtered_count || item.message_count || 0;
      });

      var barColor = echarts
        ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "#667eea" },
            { offset: 1, color: "#764ba2" },
          ])
        : "#667eea";

      chart.setOption(
        {
          tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
          legend: { data: ["平均置信度(%)", "样本数量"] },
          grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
          xAxis: { type: "category", data: labels, axisLabel: { rotate: 45 } },
          yAxis: [
            { type: "value", name: "置信度(%)", position: "left", max: 100 },
            { type: "value", name: "样本数量", position: "right" },
          ],
          series: [
            {
              name: "平均置信度(%)",
              type: "bar",
              data: confidenceData,
              itemStyle: { color: barColor },
            },
            {
              name: "样本数量",
              type: "line",
              yAxisIndex: 1,
              data: sampleData,
              itemStyle: { color: "#f093fb" },
              lineStyle: { width: 3 },
            },
          ],
        },
        true,
      );
    },

    /* ---------- 7. 用户活跃度热力图 ---------- */
    updateHeatmap() {
      var chart =
        this.chartInstances["heatmapChart"] || this.initChart("heatmapChart");
      if (!chart) return;

      var heatmapRaw = this.analyticsData.activity_heatmap || {};
      var actualData = heatmapRaw.data || [];
      var days = heatmapRaw.days || [
        "周一",
        "周二",
        "周三",
        "周四",
        "周五",
        "周六",
        "周日",
      ];
      var hours = heatmapRaw.hours || [];

      // 如果没有 hours 数据，生成默认
      if (hours.length === 0) {
        for (var i = 0; i < 24; i++) hours.push(i + ":00");
      }

      // 如果没有实际数据，生成全零
      if (actualData.length === 0) {
        for (var d = 0; d < 7; d++) {
          for (var h = 0; h < 24; h++) {
            actualData.push([h, d, 0]);
          }
        }
      }

      var maxVal = 10;
      for (var k = 0; k < actualData.length; k++) {
        if (actualData[k][2] > maxVal) maxVal = actualData[k][2];
      }

      chart.setOption(
        {
          tooltip: {
            position: "top",
            formatter: function (params) {
              return (
                days[params.value[1]] +
                " " +
                hours[params.value[0]] +
                "<br/>\u6D3B\u8DC3\u5EA6: " +
                params.value[2]
              );
            },
          },
          grid: { height: "50%", top: "10%" },
          xAxis: { type: "category", data: hours, splitArea: { show: true } },
          yAxis: { type: "category", data: days, splitArea: { show: true } },
          visualMap: {
            min: 0,
            max: maxVal,
            calculable: true,
            orient: "horizontal",
            left: "center",
            bottom: "15%",
            inRange: { color: ["#e3f2fd", "#1976d2"] },
          },
          series: [
            {
              name: "活跃度",
              type: "heatmap",
              data: actualData,
              label: { show: false },
              emphasis: {
                itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.5)" },
              },
            },
          ],
        },
        true,
      );
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
        xAxis: { type: "category", data: [] },
        yAxis: { type: "value" },
        series: [],
      };
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

    // 注册主题
    this.registerTheme();

    // 首次加载数据
    await this.fetchAllData();
    this.loading = false;

    // 等待 DOM 渲染后初始化图表
    this.$nextTick(function () {
      setTimeout(function () {
        self.updateLLMPie();
        self.updateMessageTrend();
        self.updateResponseTime();
        self.updateLearningGauge();
        self.updateSystemRadar();
        self.updateStyleChart();
        self.updateHeatmap();

        // 设置 ResizeObserver
        if (self.$refs.rootEl && typeof ResizeObserver !== "undefined") {
          self.resizeObserver = new ResizeObserver(function () {
            self.resizeAllCharts();
          });
          self.resizeObserver.observe(self.$refs.rootEl);
        }
      }, 100);
    });

    // 自动刷新 (每 5 秒)
    this.refreshTimer = setInterval(function () {
      self.refreshAll();
    }, 5000);
  },

  beforeUnmount() {
    // 清除定时器
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
    // 断开 ResizeObserver
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    // 销毁所有图表
    this.disposeAllCharts();
  },
};
