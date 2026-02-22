/**
 * Performance Monitor App
 * 3 tabs: system overview, function-level performance, on-demand profiling
 * Auto-refreshes every 10 seconds
 */
window.AppPerformanceMonitor = {
  props: { app: Object },

  template: `
    <div class="app-content" ref="rootEl">
      <!-- Loading -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载监控数据中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>
        <!-- Tab Bar -->
        <div class="tab-bar">
          <div class="tab-item" :class="{active: activeTab==='overview'}" @click="switchTab('overview')">系统概览</div>
          <div class="tab-item" :class="{active: activeTab==='functions'}" @click="switchTab('functions')">函数性能</div>
          <div class="tab-item" :class="{active: activeTab==='profiling'}" @click="switchTab('profiling')">性能分析</div>
        </div>

        <!-- ========== Tab 1: Overview ========== -->
        <template v-if="activeTab==='overview'">
          <div class="stat-grid">
            <div class="stat-card" v-for="c in healthChecks" :key="c.key">
              <div class="stat-number">{{ c.value }}</div>
              <div class="stat-label">{{ c.label }}</div>
              <div style="margin-top:6px;">
                <el-tag size="small" :type="statusTagType(c.status)">{{ statusLabel(c.status) }}</el-tag>
              </div>
              <div v-if="c.extra" style="font-size:10px;color:#86868b;margin-top:4px;">{{ c.extra }}</div>
            </div>
          </div>

          <div class="charts-grid">
            <div class="chart-box">
              <h4>CPU 使用率</h4>
              <div ref="cpuGauge" class="chart-area"></div>
            </div>
            <div class="chart-box">
              <h4>内存使用率</h4>
              <div ref="memGauge" class="chart-area"></div>
            </div>
          </div>
        </template>

        <!-- ========== Tab 2: Functions ========== -->
        <template v-if="activeTab==='functions'">
          <!-- debug_mode disabled -->
          <div v-if="functionsData && !functionsData.debug_mode" class="empty-state">
            <i class="material-icons">info</i>
            <p>函数级性能监控未启用</p>
            <p style="font-size:11px;color:#86868b;">请在插件配置中开启 debug_mode 以启用函数级性能跟踪。<br>启用后，被 @monitored 装饰的函数将记录调用次数、错误数和耗时。</p>
          </div>

          <!-- debug_mode enabled but no data -->
          <div v-else-if="functionsData && functionsData.debug_mode && filteredFunctions.length === 0 && !funcSearch" class="empty-state">
            <i class="material-icons">hourglass_empty</i>
            <p>暂无函数性能数据</p>
            <p style="font-size:11px;color:#86868b;">debug_mode 已开启，等待被监控函数被调用后将自动显示数据。</p>
          </div>

          <!-- data table -->
          <div v-else-if="functionsData && functionsData.debug_mode">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
              <el-input v-model="funcSearch" placeholder="搜索函数名..." size="small" clearable style="max-width:300px;">
                <template #prefix><i class="material-icons" style="font-size:14px;line-height:28px;">search</i></template>
              </el-input>
              <span style="font-size:11px;color:#86868b;">
                共 {{ filteredFunctions.length }} 个被监控函数 | 上次刷新: {{ formatTime(functionsData.timestamp) }}
              </span>
            </div>

            <el-table :data="filteredFunctions" size="small" stripe style="width:100%;"
                      :default-sort="{prop:'duration_avg',order:'descending'}" max-height="600">
              <el-table-column prop="name" label="函数名" min-width="280" sortable show-overflow-tooltip>
                <template #default="scope">
                  <span style="font-family:monospace;font-size:11px;" :title="scope.row.name">{{ formatFuncName(scope.row.name) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="calls" label="调用次数" width="100" sortable align="right" />
              <el-table-column prop="errors" label="错误数" width="80" sortable align="right">
                <template #default="scope">
                  <span :style="{color: scope.row.errors > 0 ? '#f44336' : 'inherit'}">{{ scope.row.errors }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="error_rate" label="错误率" width="90" sortable align="right">
                <template #default="scope">
                  <el-tag size="small" :type="scope.row.error_rate > 0.1 ? 'danger' : scope.row.error_rate > 0.01 ? 'warning' : 'success'">
                    {{ (scope.row.error_rate * 100).toFixed(1) }}%
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="duration_avg" label="平均耗时" width="110" sortable align="right">
                <template #default="scope">
                  <span style="font-family:monospace;font-weight:600;">{{ formatDuration(scope.row.duration_avg) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="duration_sum" label="总耗时" width="110" sortable align="right">
                <template #default="scope">
                  {{ formatDuration(scope.row.duration_sum) }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>

        <!-- ========== Tab 3: Profiling ========== -->
        <template v-if="activeTab==='profiling'">
          <div class="section-card">
            <h3 style="display:flex;align-items:center;gap:6px;">
              <i class="material-icons" style="font-size:16px;">speed</i>性能分析
            </h3>
            <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
              <el-radio-group v-model="profileType" size="small">
                <el-radio-button label="cpu">CPU 分析</el-radio-button>
                <el-radio-button label="memory">内存分析</el-radio-button>
              </el-radio-group>

              <template v-if="profileType === 'cpu'">
                <el-select v-model="profileBackend" size="small" style="width:120px;" placeholder="后端">
                  <el-option v-for="b in cpuBackends" :key="b" :label="b" :value="b" />
                </el-select>
                <el-select v-model="profileClockType" size="small" style="width:100px;">
                  <el-option label="Wall" value="wall" />
                  <el-option label="CPU" value="cpu" />
                </el-select>
              </template>
              <template v-else>
                <span style="font-size:12px;color:#86868b;">栈帧深度:</span>
                <el-input-number v-model="profileNFrames" size="small" :min="1" :max="50" style="width:100px;" />
              </template>
            </div>

            <div style="display:flex;gap:8px;align-items:center;">
              <el-button v-if="!activeSession" type="primary" size="small" @click="startProfile" :loading="profileLoading">
                <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;">play_arrow</i>
                开始分析
              </el-button>
              <template v-else>
                <el-button type="danger" size="small" @click="stopProfile" :loading="profileLoading">
                  <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;">stop</i>
                  停止并查看结果
                </el-button>
                <span style="font-size:11px;color:#86868b;">
                  会话: {{ activeSession.session_id }} | 类型: {{ activeSession.type }}
                </span>
              </template>
            </div>
          </div>

          <!-- Profiling Results -->
          <div v-if="profileResult" class="section-card" style="margin-top:12px;">
            <h3>分析结果</h3>
            <div style="font-size:12px;color:#86868b;margin-bottom:8px;">
              后端: {{ profileResult.backend || 'tracemalloc' }} |
              耗时: {{ (profileResult.duration_s || 0).toFixed(2) }}s
              <template v-if="profileResult.clock_type"> | 时钟: {{ profileResult.clock_type }}</template>
              <template v-if="profileResult.current_kb"> | 当前: {{ profileResult.current_kb.toFixed(1) }}KB | 峰值: {{ profileResult.peak_kb.toFixed(1) }}KB</template>
            </div>

            <!-- CPU results -->
            <el-table v-if="profileResult.top_functions" :data="profileResult.top_functions" size="small" stripe max-height="400"
                      :default-sort="{prop: profileResult.backend === 'yappi' ? 'ttot' : 'cumtime', order: 'descending'}">
              <el-table-column prop="name" label="函数" min-width="200" show-overflow-tooltip sortable>
                <template #default="scope">
                  <span style="font-family:monospace;font-size:11px;" :title="scope.row.name">{{ scope.row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="ncall" label="调用次数" width="100" align="right" sortable>
                <template #default="scope">{{ scope.row.ncall != null ? scope.row.ncall : 0 }}</template>
              </el-table-column>
              <el-table-column v-if="profileResult.backend==='yappi'" prop="tsub" label="自身耗时(s)" width="120" align="right" sortable>
                <template #default="scope">{{ (scope.row.tsub || 0).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column v-if="profileResult.backend==='yappi'" prop="ttot" label="总耗时(s)" width="110" align="right" sortable>
                <template #default="scope">{{ (scope.row.ttot || 0).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column v-if="profileResult.backend==='yappi'" prop="tavg" label="平均(s)" width="100" align="right" sortable>
                <template #default="scope">{{ (scope.row.tavg || 0).toFixed(6) }}</template>
              </el-table-column>
              <el-table-column v-if="profileResult.backend==='cProfile'" prop="tottime" label="自身耗时(s)" width="120" align="right" sortable>
                <template #default="scope">{{ (scope.row.tottime || 0).toFixed(4) }}</template>
              </el-table-column>
              <el-table-column v-if="profileResult.backend==='cProfile'" prop="cumtime" label="累计耗时(s)" width="120" align="right" sortable>
                <template #default="scope">{{ (scope.row.cumtime || 0).toFixed(4) }}</template>
              </el-table-column>
            </el-table>

            <!-- Memory results -->
            <el-table v-if="profileResult.top_allocations" :data="profileResult.top_allocations" size="small" stripe max-height="400"
                      :default-sort="{prop:'size_kb',order:'descending'}">
              <el-table-column prop="location" label="位置" min-width="200" show-overflow-tooltip sortable>
                <template #default="scope">
                  <span style="font-family:monospace;font-size:11px;" :title="scope.row.location">{{ scope.row.location }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="size_kb" label="大小(KB)" width="120" align="right" sortable>
                <template #default="scope">{{ scope.row.size_kb != null ? scope.row.size_kb.toFixed(2) : 0 }}</template>
              </el-table-column>
              <el-table-column prop="count" label="分配次数" width="120" align="right" sortable />
            </el-table>
          </div>

          <div v-else-if="!activeSession" class="empty-state" style="margin-top:20px;">
            <i class="material-icons">timer</i>
            <p>点击"开始分析"启动性能分析会话</p>
            <p style="font-size:11px;color:#86868b;">CPU 分析会记录函数调用耗时，内存分析会追踪内存分配热点。</p>
          </div>
        </template>
      </template>
    </div>
  `,

  data() {
    return {
      loading: true,
      activeTab: "functions",

      healthData: null,
      metricsData: null,
      functionsData: null,
      funcSearch: "",

      availableBackends: [],
      profileType: "cpu",
      profileBackend: "",
      profileClockType: "wall",
      profileNFrames: 10,
      activeSession: null,
      profileResult: null,
      profileLoading: false,

      chartInstances: {},
      refreshTimer: null,
      resizeObserver: null,
      themeRegistered: false,
    };
  },

  computed: {
    filteredFunctions() {
      if (!this.functionsData || !this.functionsData.functions) return [];
      var list = this.functionsData.functions.map(function (f) {
        return {
          name: f.name,
          calls: f.calls,
          errors: f.errors,
          error_rate: f.error_rate,
          duration_avg: f.duration ? f.duration.avg : 0,
          duration_sum: f.duration ? f.duration.sum : 0,
          duration_count: f.duration ? f.duration.count : 0,
        };
      });
      var search = this.funcSearch.toLowerCase();
      if (search) {
        list = list.filter(function (f) {
          return f.name.toLowerCase().indexOf(search) !== -1;
        });
      }
      return list;
    },

    healthChecks() {
      if (!this.healthData || !this.healthData.checks) return [];
      var checks = this.healthData.checks;
      var result = [];

      if (checks.cpu) {
        result.push({
          key: "cpu",
          label: "CPU",
          value:
            checks.cpu.detail && checks.cpu.detail.cpu_percent != null
              ? checks.cpu.detail.cpu_percent.toFixed(1) + "%"
              : "-",
          status: checks.cpu.status,
        });
      }
      if (checks.memory) {
        var md = checks.memory.detail || {};
        result.push({
          key: "memory",
          label: "内存",
          value:
            md.memory_percent != null
              ? md.memory_percent.toFixed(1) + "%"
              : "-",
          status: checks.memory.status,
          extra:
            md.used_gb != null
              ? md.used_gb.toFixed(1) + " / " + md.total_gb.toFixed(1) + " GB"
              : "",
        });
      }
      if (checks.llm) {
        var ld = checks.llm.detail || {};
        result.push({
          key: "llm",
          label: "LLM",
          value:
            ld.error_rate != null
              ? (ld.error_rate * 100).toFixed(1) + "%"
              : "-",
          status: checks.llm.status,
          extra:
            ld.avg_latency_s != null
              ? "延迟 " + ld.avg_latency_s.toFixed(2) + "s"
              : "",
        });
      }
      if (checks.cache) {
        var cd = checks.cache.detail || {};
        result.push({
          key: "cache",
          label: "缓存",
          value:
            cd.hit_rate != null ? (cd.hit_rate * 100).toFixed(1) + "%" : "-",
          status: checks.cache.status,
          extra:
            cd.total_hits != null
              ? "命中 " + cd.total_hits + " / 未命中 " + cd.total_misses
              : "",
        });
      }
      if (checks.services) {
        var sd = checks.services.detail || {};
        result.push({
          key: "services",
          label: "服务",
          value: sd.total != null ? sd.total + " 个" : "-",
          status: checks.services.status,
          extra:
            sd.error_services && sd.error_services.length > 0
              ? "异常: " + sd.error_services.join(", ")
              : "",
        });
      }
      return result;
    },

    cpuBackends() {
      return this.availableBackends.filter(function (b) {
        return b !== "tracemalloc";
      });
    },
  },

  methods: {
    formatFuncName(name) {
      var parts = name.split(".");
      if (parts.length <= 3) return name;
      return "..." + parts.slice(-2).join(".");
    },

    formatDuration(seconds) {
      if (seconds == null) return "-";
      if (seconds < 0.001) return (seconds * 1000000).toFixed(0) + "\u00b5s";
      if (seconds < 1) return (seconds * 1000).toFixed(1) + "ms";
      return seconds.toFixed(2) + "s";
    },

    formatTime(ts) {
      if (!ts) return "-";
      return new Date(ts * 1000).toLocaleTimeString();
    },

    statusTagType(status) {
      if (status === "healthy") return "success";
      if (status === "degraded") return "warning";
      return "danger";
    },

    statusLabel(status) {
      if (status === "healthy") return "\u6b63\u5e38";
      if (status === "degraded") return "\u8b66\u544a";
      return "\u5f02\u5e38";
    },

    /* ---------- Charts ---------- */

    registerTheme() {
      if (this.themeRegistered) return;
      var echarts = window.echarts;
      if (!echarts) return;
      try {
        echarts.registerTheme("perf-monitor", {
          backgroundColor: "transparent",
          textStyle: {
            fontFamily: "Roboto, sans-serif",
            fontSize: 12,
            color: "#424242",
          },
        });
        this.themeRegistered = true;
      } catch (e) {
        /* ignore */
      }
    },

    initChart(refName) {
      var echarts = window.echarts;
      if (!echarts) return null;
      var dom = this.$refs[refName];
      if (!dom) return null;
      var existing = echarts.getInstanceByDom(dom);
      if (existing) existing.dispose();
      var chart = echarts.init(dom, "perf-monitor");
      this.chartInstances[refName] = chart;
      return chart;
    },

    updateCpuGauge() {
      var chart = this.chartInstances["cpuGauge"] || this.initChart("cpuGauge");
      if (!chart) return;
      var val = 0;
      if (this.metricsData && this.metricsData.metrics) {
        val = this.metricsData.metrics["system_cpu_percent"] || 0;
      }
      chart.setOption(
        {
          series: [
            {
              type: "gauge",
              startAngle: 220,
              endAngle: -40,
              min: 0,
              max: 100,
              progress: { show: true, width: 12 },
              axisLine: {
                lineStyle: {
                  width: 12,
                  color: [
                    [0.7, "#4caf50"],
                    [0.9, "#ff9800"],
                    [1, "#f44336"],
                  ],
                },
              },
              axisTick: { show: false },
              splitLine: { length: 8, lineStyle: { width: 2 } },
              axisLabel: { distance: 18, fontSize: 10 },
              pointer: { length: "60%", width: 4 },
              detail: {
                formatter: "{value}%",
                fontSize: 18,
                offsetCenter: [0, "70%"],
              },
              title: { offsetCenter: [0, "90%"], fontSize: 12 },
              data: [{ value: val.toFixed(1), name: "CPU" }],
            },
          ],
        },
        true,
      );
    },

    updateMemGauge() {
      var chart = this.chartInstances["memGauge"] || this.initChart("memGauge");
      if (!chart) return;
      var val = 0;
      if (this.metricsData && this.metricsData.metrics) {
        val = this.metricsData.metrics["system_memory_percent"] || 0;
      }
      chart.setOption(
        {
          series: [
            {
              type: "gauge",
              startAngle: 220,
              endAngle: -40,
              min: 0,
              max: 100,
              progress: { show: true, width: 12 },
              axisLine: {
                lineStyle: {
                  width: 12,
                  color: [
                    [0.7, "#4caf50"],
                    [0.85, "#ff9800"],
                    [1, "#f44336"],
                  ],
                },
              },
              axisTick: { show: false },
              splitLine: { length: 8, lineStyle: { width: 2 } },
              axisLabel: { distance: 18, fontSize: 10 },
              pointer: { length: "60%", width: 4 },
              detail: {
                formatter: "{value}%",
                fontSize: 18,
                offsetCenter: [0, "70%"],
              },
              title: { offsetCenter: [0, "90%"], fontSize: 12 },
              data: [{ value: val.toFixed(1), name: "\u5185\u5b58" }],
            },
          ],
        },
        true,
      );
    },

    resizeAllCharts() {
      for (var key in this.chartInstances) {
        if (this.chartInstances[key]) {
          this.chartInstances[key].resize();
        }
      }
    },

    disposeAllCharts() {
      for (var key in this.chartInstances) {
        if (this.chartInstances[key]) {
          this.chartInstances[key].dispose();
        }
      }
      this.chartInstances = {};
    },

    /* ---------- Data Fetching ---------- */

    async fetchAllData() {
      try {
        var results = await Promise.allSettled([
          fetch("/api/monitoring/health").then(function (r) {
            return r.json();
          }),
          fetch("/api/monitoring/metrics/json").then(function (r) {
            return r.json();
          }),
          fetch("/api/monitoring/functions").then(function (r) {
            return r.json();
          }),
        ]);
        if (results[0].status === "fulfilled")
          this.healthData = results[0].value;
        if (results[1].status === "fulfilled")
          this.metricsData = results[1].value;
        if (results[2].status === "fulfilled")
          this.functionsData = results[2].value;
      } catch (e) {
        console.error("[PerformanceMonitor] fetchAllData error:", e);
      }
    },

    async refreshAll() {
      await this.fetchAllData();
      if (this.activeTab === "overview") {
        this.updateCpuGauge();
        this.updateMemGauge();
      }
    },

    switchTab(tab) {
      this.activeTab = tab;
      if (tab === "overview") {
        var self = this;
        this.$nextTick(function () {
          setTimeout(function () {
            self.updateCpuGauge();
            self.updateMemGauge();
          }, 50);
        });
      }
    },

    /* ---------- Profiling ---------- */

    async startProfile() {
      this.profileLoading = true;
      try {
        var body = { type: this.profileType };
        if (this.profileType === "cpu") {
          body.backend = this.profileBackend;
          body.clock_type = this.profileClockType;
        } else {
          body.n_frames = this.profileNFrames;
        }
        var resp = await fetch("/api/monitoring/profile/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (resp.ok) {
          this.activeSession = data;
          this.profileResult = null;
        }
      } catch (e) {
        console.error("[PerformanceMonitor] startProfile error:", e);
      } finally {
        this.profileLoading = false;
      }
    },

    async stopProfile() {
      if (!this.activeSession) return;
      this.profileLoading = true;
      try {
        var url =
          "/api/monitoring/profile/" +
          this.activeSession.session_id +
          "?type=" +
          this.activeSession.type;
        var resp = await fetch(url, { credentials: "same-origin" });
        var data = await resp.json();
        if (resp.ok) {
          this.profileResult = data;
        }
        this.activeSession = null;
      } catch (e) {
        console.error("[PerformanceMonitor] stopProfile error:", e);
      } finally {
        this.profileLoading = false;
      }
    },
  },

  async mounted() {
    var self = this;
    this.registerTheme();

    try {
      var resp = await fetch("/api/monitoring/profile/backends", {
        credentials: "same-origin",
      });
      var data = await resp.json();
      this.availableBackends = data.backends || [];
      var cpuBk = this.availableBackends.find(function (b) {
        return b !== "tracemalloc";
      });
      if (cpuBk) this.profileBackend = cpuBk;
    } catch (e) {
      /* ignore */
    }

    await this.fetchAllData();
    this.loading = false;

    this.$nextTick(function () {
      setTimeout(function () {
        if (self.activeTab === "overview") {
          self.updateCpuGauge();
          self.updateMemGauge();
        }
        if (self.$refs.rootEl && typeof ResizeObserver !== "undefined") {
          self.resizeObserver = new ResizeObserver(function () {
            self.resizeAllCharts();
          });
          self.resizeObserver.observe(self.$refs.rootEl);
        }
      }, 100);
    });

    this.refreshTimer = setInterval(function () {
      self.refreshAll();
    }, 10000);
  },

  beforeUnmount() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    this.disposeAllCharts();
  },
};
