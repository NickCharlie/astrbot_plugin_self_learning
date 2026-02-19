/**
 * 社交关系分析 - Social Relations App
 * Two-stage view: group list -> group detail (relationship graph + member list).
 * Uses ECharts force-directed / circular graph for relationship visualization.
 * Auto-refreshes every 30s when on the detail page.
 */
window.AppSocialRelations = {
  props: { app: Object },

  template: `
    <div class="app-content" ref="rootEl">
      <!-- Loading State -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载数据中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>

        <!-- ================================================================ -->
        <!-- Stage 1: Group List                                              -->
        <!-- ================================================================ -->
        <template v-if="!currentGroupId">
          <!-- Page Title -->
          <div style="margin-bottom:16px;">
            <h2 style="margin:0 0 4px;font-size:18px;font-weight:600;color:#1d1d1f;">社交关系分析</h2>
            <p style="margin:0;font-size:12px;color:#86868b;">可视化群组成员社交关系图谱，选择群组查看详情</p>
          </div>

          <!-- Group Cards Grid -->
          <div v-if="groups.length > 0" class="group-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-bottom:16px;">
            <div v-for="group in groups" :key="group.group_id"
              @click="loadGroupRelations(group.group_id, group.group_name)"
              style="background:#fff;border-radius:10px;padding:16px;border:1px solid #e5e5e5;cursor:pointer;transition:all 0.2s;"
              @mouseenter="$event.currentTarget.style.borderColor='#007aff';$event.currentTarget.style.boxShadow='0 2px 8px rgba(0,122,255,0.12)'"
              @mouseleave="$event.currentTarget.style.borderColor='#e5e5e5';$event.currentTarget.style.boxShadow='none'">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <i class="material-icons" style="font-size:22px;color:#007aff;">group</i>
                <span style="font-size:14px;font-weight:600;color:#1d1d1f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ group.group_name || '群组 ' + group.group_id }}</span>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:12px;color:#86868b;">成员数量</span>
                <span style="font-size:16px;font-weight:700;color:#1d1d1f;">{{ group.member_count || 0 }}</span>
              </div>
              <div style="margin-top:8px;text-align:right;">
                <span style="font-size:11px;color:#007aff;font-weight:500;">查看详情 <i class="material-icons" style="font-size:12px;vertical-align:-2px;">arrow_forward</i></span>
              </div>
            </div>
          </div>

          <!-- Empty State -->
          <div v-else class="empty-state" style="margin-bottom:12px;">
            <i class="material-icons">group_off</i>
            <p>暂无群组数据，请先确保插件已收集到群消息</p>
          </div>
        </template>

        <!-- ================================================================ -->
        <!-- Stage 2: Group Detail                                            -->
        <!-- ================================================================ -->
        <template v-if="currentGroupId">

          <!-- Back Button + Group Name Header -->
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
            <button @click="goBack"
              style="display:flex;align-items:center;gap:4px;padding:6px 12px;background:#fff;border:1px solid #e5e5e5;border-radius:8px;cursor:pointer;font-size:12px;color:#007aff;transition:all 0.2s;"
              @mouseenter="$event.currentTarget.style.background='#f0f0f5'"
              @mouseleave="$event.currentTarget.style.background='#fff'">
              <i class="material-icons" style="font-size:16px;">arrow_back</i>
              返回
            </button>
            <div>
              <h2 style="margin:0;font-size:18px;font-weight:600;color:#1d1d1f;">{{ currentGroupName || '群组 ' + currentGroupId }}</h2>
              <p style="margin:2px 0 0;font-size:11px;color:#86868b;">群组 ID: {{ currentGroupId }}</p>
            </div>
          </div>

          <!-- 4 Stat Cards -->
          <div class="stat-grid">
            <div class="stat-card">
              <div class="stat-number">{{ stats.total_members || 0 }}</div>
              <div class="stat-label">总成员数</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ stats.total_relations || 0 }}</div>
              <div class="stat-label">关系数量</div>
            </div>
            <div class="stat-card">
              <div class="stat-number" style="font-size:16px;">{{ stats.most_active || '暂无' }}</div>
              <div class="stat-label">最活跃成员</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ formatStrength(stats.avg_strength) }}</div>
              <div class="stat-label">平均关系强度</div>
            </div>
          </div>

          <!-- Action Bar -->
          <div class="filter-bar">
            <el-button type="primary" size="small" :loading="analyzing" @click="analyzeGroup">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;" v-if="!analyzing">analytics</i>
              分析关系
            </el-button>
            <el-button type="danger" size="small" @click="clearGroupRelations">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;">delete_sweep</i>
              清除数据
            </el-button>
            <div style="flex:1;"></div>
            <select v-model="selectedUserId" @change="onUserFilterChange"
              style="padding:5px 10px;border:1px solid #e0e0e0;border-radius:6px;font-size:12px;background:#fff;color:#333;cursor:pointer;max-width:200px;">
              <option value="">全部成员</option>
              <option v-for="m in members" :key="m.user_id" :value="m.user_id">{{ m.nickname || m.user_id }}</option>
            </select>
            <div style="display:flex;align-items:center;gap:4px;background:#fff;border-radius:6px;padding:2px;border:1px solid #e5e5e5;">
              <span @click="setLayout('force')"
                :style="{
                  padding:'4px 10px',fontSize:'11px',borderRadius:'4px',cursor:'pointer',
                  background: graphLayout === 'force' ? '#007aff' : 'transparent',
                  color: graphLayout === 'force' ? '#fff' : '#86868b',
                  fontWeight: graphLayout === 'force' ? '600' : '400',
                  transition:'all 0.2s'
                }">力导向</span>
              <span @click="setLayout('circular')"
                :style="{
                  padding:'4px 10px',fontSize:'11px',borderRadius:'4px',cursor:'pointer',
                  background: graphLayout === 'circular' ? '#007aff' : 'transparent',
                  color: graphLayout === 'circular' ? '#fff' : '#86868b',
                  fontWeight: graphLayout === 'circular' ? '600' : '400',
                  transition:'all 0.2s'
                }">环形</span>
            </div>
          </div>

          <!-- Relationship Graph -->
          <div class="chart-box">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <h4 style="margin:0;">
                <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:4px;">hub</i>
                社交关系图谱
                <span v-if="selectedUserId" style="font-size:11px;color:#86868b;margin-left:6px;">
                  (筛选: {{ getSelectedUserName() }})
                </span>
              </h4>
              <span style="font-size:11px;color:#86868b;">
                {{ (displayData.nodes || []).length }} 节点 / {{ (displayData.links || []).length }} 关系
              </span>
            </div>
            <div ref="relationChart" class="chart-area" style="height:420px;"></div>
          </div>

          <!-- Members List -->
          <div class="section-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
              <h3 style="margin:0;display:flex;align-items:center;">
                <i class="material-icons" style="font-size:16px;margin-right:4px;">people</i>
                成员列表
                <span style="font-size:11px;color:#86868b;font-weight:400;margin-left:6px;">({{ filteredMembers.length }})</span>
              </h3>
              <input type="text" v-model="memberSearch" placeholder="搜索成员昵称..."
                style="padding:6px 12px;border:1px solid #e0e0e0;border-radius:6px;font-size:12px;outline:none;background:#fafafa;color:#333;width:200px;" />
            </div>

            <div v-if="filteredMembers.length > 0" style="max-height:360px;overflow-y:auto;">
              <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <thead>
                  <tr style="border-bottom:2px solid #f0f0f0;">
                    <th style="text-align:left;padding:8px 10px;color:#86868b;font-weight:500;">昵称</th>
                    <th style="text-align:center;padding:8px 10px;color:#86868b;font-weight:500;">消息数</th>
                    <th style="text-align:center;padding:8px 10px;color:#86868b;font-weight:500;">关系数</th>
                    <th style="text-align:center;padding:8px 10px;color:#86868b;font-weight:500;">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in filteredMembers" :key="m.user_id"
                    style="border-bottom:1px solid #f5f5f5;transition:background 0.15s;"
                    @mouseenter="$event.currentTarget.style.background='#f9f9fb'"
                    @mouseleave="$event.currentTarget.style.background='transparent'">
                    <td style="padding:8px 10px;font-weight:500;color:#1d1d1f;">
                      <div style="display:flex;align-items:center;gap:6px;">
                        <i class="material-icons" style="font-size:16px;color:#007aff;">person</i>
                        {{ m.nickname || m.user_id }}
                      </div>
                    </td>
                    <td style="text-align:center;padding:8px 10px;color:#333;">{{ m.message_count || 0 }}</td>
                    <td style="text-align:center;padding:8px 10px;color:#333;">{{ getMemberRelationCount(m.user_id) }}</td>
                    <td style="text-align:center;padding:8px 10px;">
                      <button @click="filterByUser(m.user_id)"
                        style="padding:3px 10px;background:#e8f0fe;color:#007aff;border:none;border-radius:4px;font-size:11px;cursor:pointer;transition:background 0.15s;"
                        @mouseenter="$event.currentTarget.style.background='#d0e2fc'"
                        @mouseleave="$event.currentTarget.style.background='#e8f0fe'">
                        <i class="material-icons" style="font-size:12px;vertical-align:-2px;">filter_alt</i>
                        筛选
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else style="text-align:center;padding:24px 0;color:#86868b;font-size:12px;">
              <i class="material-icons" style="font-size:32px;display:block;margin-bottom:8px;opacity:0.4;">person_search</i>
              暂无成员数据
            </div>
          </div>
        </template>

        <!-- Social Links Footer -->
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

      // Stage 1: group list
      groups: [],

      // Stage 2: group detail
      currentGroupId: null,
      currentGroupName: "",
      stats: {},
      members: [],
      relations: [],
      displayData: { nodes: [], links: [] },

      // UI state
      graphLayout: "force",
      selectedUserId: "",
      memberSearch: "",
      analyzing: false,

      // Chart
      chartInstance: null,
      resizeObserver: null,
      themeRegistered: false,

      // Auto-refresh
      refreshTimer: null,

      // AbortController for in-flight requests
      abortController: null,
    };
  },

  computed: {
    /** Filter members list by search keyword */
    filteredMembers() {
      var keyword = (this.memberSearch || "").trim().toLowerCase();
      if (!keyword) return this.members;
      return this.members.filter(function (m) {
        var name = (m.nickname || m.user_id || "").toLowerCase();
        return name.indexOf(keyword) !== -1;
      });
    },
  },

  methods: {
    /* ========== Utility Functions ========== */

    formatStrength(v) {
      if (v == null || v === undefined) return "0";
      var num = Number(v);
      if (isNaN(num)) return "0";
      return num.toFixed(2);
    },

    getSelectedUserName() {
      if (!this.selectedUserId) return "";
      var found = this.members.find(
        function (m) {
          return m.user_id === this.selectedUserId;
        }.bind(this),
      );
      return found ? found.nickname || found.user_id : this.selectedUserId;
    },

    getMemberRelationCount(userId) {
      var count = 0;
      this.relations.forEach(function (r) {
        if (
          r.source === userId ||
          r.target === userId ||
          r.source_id === userId ||
          r.target_id === userId
        ) {
          count++;
        }
      });
      return count;
    },

    /** Create a new AbortController, cancelling any existing one */
    newAbortController() {
      if (this.abortController) {
        this.abortController.abort();
      }
      this.abortController = new AbortController();
      return this.abortController;
    },

    /* ========== ECharts Theme ========== */

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
        console.warn("[SocialRelations] registerTheme failed", e);
      }
    },

    /* ========== Chart Instance Management ========== */

    initChart() {
      var echarts = window.echarts;
      if (!echarts) return null;
      var dom = this.$refs.relationChart;
      if (!dom) return null;
      var existing = echarts.getInstanceByDom(dom);
      if (existing) {
        existing.dispose();
      }
      var chart = echarts.init(dom, "material");
      this.chartInstance = chart;
      return chart;
    },

    disposeChart() {
      if (this.chartInstance && !this.chartInstance.isDisposed()) {
        this.chartInstance.dispose();
      }
      this.chartInstance = null;
    },

    resizeChart() {
      if (this.chartInstance && !this.chartInstance.isDisposed()) {
        this.chartInstance.resize();
      }
    },

    /* ========== Data Loading ========== */

    /** Stage 1: Load group list */
    async loadGroups() {
      var ctrl = this.newAbortController();
      try {
        var resp = await fetch("/api/social_relations/groups", {
          signal: ctrl.signal,
        });
        var data = await resp.json();
        this.groups = Array.isArray(data) ? data : data.groups || [];
      } catch (e) {
        if (e.name === "AbortError") return;
        console.error("[SocialRelations] loadGroups error:", e);
        this.groups = [];
      }
    },

    /** Stage 2: Load group detail (relations, members, stats) */
    async loadGroupRelations(groupId, groupName) {
      this.currentGroupId = groupId;
      this.currentGroupName = groupName || "";
      this.selectedUserId = "";
      this.memberSearch = "";
      this.loading = true;

      var ctrl = this.newAbortController();
      try {
        var resp = await fetch(
          "/api/social_relations/" + encodeURIComponent(groupId),
          { signal: ctrl.signal },
        );
        var data = await resp.json();

        this.members = data.members || [];
        this.relations = data.relations || [];

        // Build stats from flat response fields
        var totalMembers = data.member_count || this.members.length;
        var totalRelations = data.relation_count || this.relations.length;

        // Calculate most active member
        var mostActive = "暂无";
        var maxMsg = 0;
        this.members.forEach(function (m) {
          if ((m.message_count || 0) > maxMsg) {
            maxMsg = m.message_count;
            mostActive = m.nickname || m.user_id;
          }
        });

        // Calculate average relation strength
        var avgStrength = 0;
        if (this.relations.length > 0) {
          var totalStrength = 0;
          this.relations.forEach(function (r) {
            totalStrength += r.strength || r.weight || 0;
          });
          avgStrength = totalStrength / this.relations.length;
        }

        this.stats = data.stats || {
          total_members: totalMembers,
          total_relations: totalRelations,
          most_active: mostActive,
          avg_strength: avgStrength,
        };

        // Build display data from full dataset
        this.buildDisplayData(this.members, this.relations);
      } catch (e) {
        if (e.name === "AbortError") return;
        console.error("[SocialRelations] loadGroupRelations error:", e);
        this.members = [];
        this.relations = [];
        this.stats = {};
        this.displayData = { nodes: [], links: [] };
        if (typeof ElementPlus !== "undefined") {
          ElementPlus.ElMessage.error(
            "加载群组关系失败: " + (e.message || "网络错误"),
          );
        }
      } finally {
        this.loading = false;
      }

      // Render chart after DOM update
      var self = this;
      this.$nextTick(function () {
        setTimeout(function () {
          self.renderRelationChart();
          self.setupResizeObserver();
        }, 100);
      });

      // Start auto-refresh timer (30s)
      this.startAutoRefresh();
    },

    /** Reload current group data silently (for auto-refresh) */
    async reloadCurrentGroup() {
      if (!this.currentGroupId) return;
      var ctrl = this.newAbortController();
      try {
        var resp = await fetch(
          "/api/social_relations/" + encodeURIComponent(this.currentGroupId),
          { signal: ctrl.signal },
        );
        var data = await resp.json();

        this.members = data.members || [];
        this.relations = data.relations || [];

        // Build stats from flat response fields
        var totalMembers = data.member_count || this.members.length;
        var totalRelations = data.relation_count || this.relations.length;

        // Calculate most active member
        var mostActive = "暂无";
        var maxMsg = 0;
        this.members.forEach(function (m) {
          if ((m.message_count || 0) > maxMsg) {
            maxMsg = m.message_count;
            mostActive = m.nickname || m.user_id;
          }
        });

        // Calculate average relation strength
        var avgStrength = 0;
        if (this.relations.length > 0) {
          var totalStrength = 0;
          this.relations.forEach(function (r) {
            totalStrength += r.strength || r.weight || 0;
          });
          avgStrength = totalStrength / this.relations.length;
        }

        this.stats = data.stats || {
          total_members: totalMembers,
          total_relations: totalRelations,
          most_active: mostActive,
          avg_strength: avgStrength,
        };

        // If a user filter is active, re-apply it
        if (this.selectedUserId) {
          this.applyUserFilter(this.selectedUserId);
        } else {
          this.buildDisplayData(this.members, this.relations);
        }

        this.renderRelationChart();
      } catch (e) {
        if (e.name === "AbortError") return;
        console.error("[SocialRelations] reloadCurrentGroup error:", e);
      }
    },

    /* ========== Display Data Building ========== */

    /** Build nodes and links from members and relations */
    buildDisplayData(members, relations) {
      // Build a user_id -> nickname map
      var nameMap = {};
      members.forEach(function (m) {
        nameMap[m.user_id] = m.nickname || String(m.user_id);
      });

      var nodes = members.map(function (m) {
        return {
          name: m.nickname || String(m.user_id),
          id: String(m.user_id),
          symbolSize: Math.max(20, Math.min(80, (m.message_count || 0) / 5)),
          value: m.message_count || 0,
          category: 0,
          itemStyle: {
            color: "#1976d2",
          },
        };
      });

      var links = relations.map(function (r) {
        var sourceName =
          nameMap[r.source] ||
          nameMap[r.source_id] ||
          String(r.source || r.source_id);
        var targetName =
          nameMap[r.target] ||
          nameMap[r.target_id] ||
          String(r.target || r.target_id);
        return {
          source: sourceName,
          target: targetName,
          value: r.strength || r.weight || 1,
          lineStyle: {
            width: Math.max(1, Math.min(10, (r.strength || r.weight || 1) * 2)),
            opacity: 0.6,
          },
        };
      });

      this.displayData = { nodes: nodes, links: links };
    },

    /* ========== Chart Rendering ========== */

    renderRelationChart() {
      var chart = this.chartInstance || this.initChart();
      if (!chart) return;

      var nodes = this.displayData.nodes || [];
      var links = this.displayData.links || [];

      if (nodes.length === 0) {
        chart.setOption(
          {
            title: {
              text: "暂无关系数据",
              subtext: '点击"分析关系"按钮开始分析',
              left: "center",
              top: "middle",
              textStyle: { fontSize: 14, color: "#999" },
              subtextStyle: { fontSize: 12, color: "#bbb" },
            },
            series: [],
          },
          true,
        );
        return;
      }

      var isCircular = this.graphLayout === "circular";

      var seriesConfig = {
        type: "graph",
        layout: isCircular ? "circular" : "force",
        roam: true,
        draggable: true,
        data: nodes,
        links: links,
        label: {
          show: true,
          position: "right",
          fontSize: 10,
          color: "#333",
          formatter: "{b}",
        },
        emphasis: {
          focus: "adjacency",
          label: {
            show: true,
            fontSize: 13,
            fontWeight: "bold",
          },
          lineStyle: {
            width: 4,
            opacity: 1,
          },
        },
        lineStyle: {
          color: "source",
          curveness: 0.2,
        },
      };

      if (isCircular) {
        seriesConfig.circular = {
          rotateLabel: true,
        };
      } else {
        seriesConfig.force = {
          repulsion: 200,
          gravity: 0.1,
          edgeLength: [50, 200],
          layoutAnimation: true,
        };
      }

      var option = {
        tooltip: {
          trigger: "item",
          formatter: function (params) {
            if (params.dataType === "node") {
              return (
                "<b>" + params.name + "</b><br/>消息数: " + (params.value || 0)
              );
            }
            if (params.dataType === "edge") {
              return (
                params.data.source +
                " <-> " +
                params.data.target +
                "<br/>关系强度: " +
                (params.data.value || 0)
              );
            }
            return "";
          },
        },
        animationDuration: 1000,
        animationEasingUpdate: "quinticInOut",
        series: [seriesConfig],
      };

      chart.setOption(option, true);
    },

    /* ========== Layout Toggle ========== */

    setLayout(layout) {
      this.graphLayout = layout;
      this.renderRelationChart();
    },

    /* ========== User Filter ========== */

    onUserFilterChange() {
      if (this.selectedUserId) {
        this.filterByUser(this.selectedUserId);
      } else {
        // Reset to full data
        this.buildDisplayData(this.members, this.relations);
        this.renderRelationChart();
      }
    },

    async filterByUser(userId) {
      this.selectedUserId = userId;

      var ctrl = this.newAbortController();
      try {
        var resp = await fetch(
          "/api/social_relations/" +
            encodeURIComponent(this.currentGroupId) +
            "/user/" +
            encodeURIComponent(userId),
          { signal: ctrl.signal },
        );
        var data = await resp.json();

        // Build filtered display data from user-specific relations
        var userRelations = data.relations || [];
        this.applyUserFilter(userId, userRelations);
        this.renderRelationChart();
      } catch (e) {
        if (e.name === "AbortError") return;
        console.error("[SocialRelations] filterByUser error:", e);
        // Fall back to local filtering
        this.applyUserFilter(userId);
        this.renderRelationChart();
      }
    },

    /** Apply user filter locally from existing data */
    applyUserFilter(userId, userRelations) {
      var relations =
        userRelations ||
        this.relations.filter(function (r) {
          return (
            r.source === userId ||
            r.target === userId ||
            r.source_id === userId ||
            r.target_id === userId
          );
        });

      // Collect involved user IDs
      var involvedIds = {};
      involvedIds[userId] = true;
      relations.forEach(function (r) {
        var src = r.source || r.source_id;
        var tgt = r.target || r.target_id;
        if (src) involvedIds[src] = true;
        if (tgt) involvedIds[tgt] = true;
      });

      // Filter members to only those involved
      var filteredMembers = this.members.filter(function (m) {
        return involvedIds[m.user_id];
      });

      this.buildDisplayData(filteredMembers, relations);
    },

    /* ========== Analyze Group ========== */

    async analyzeGroup() {
      if (!this.currentGroupId) return;

      this.analyzing = true;
      try {
        var resp = await fetch(
          "/api/social_relations/" +
            encodeURIComponent(this.currentGroupId) +
            "/analyze",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message_limit: 200, force_refresh: true }),
          },
        );

        var result = await resp.json();

        if (resp.ok) {
          if (typeof ElementPlus !== "undefined") {
            ElementPlus.ElMessage.success("关系分析已完成");
          }
          // Reload data
          await this.reloadCurrentGroup();
        } else {
          var errMsg = (result && result.error) || "分析失败，请重试";
          if (typeof ElementPlus !== "undefined") {
            ElementPlus.ElMessage.error(errMsg);
          }
        }
      } catch (e) {
        console.error("[SocialRelations] analyzeGroup error:", e);
        if (typeof ElementPlus !== "undefined") {
          ElementPlus.ElMessage.error(
            "分析请求失败: " + (e.message || "网络错误"),
          );
        }
      } finally {
        this.analyzing = false;
      }
    },

    /* ========== Clear Group Relations (Double Confirm) ========== */

    clearGroupRelations() {
      if (!this.currentGroupId) return;
      var self = this;
      var groupName = this.currentGroupName || this.currentGroupId;

      ElementPlus.ElMessageBox.confirm(
        '确定要清除群组"' +
          groupName +
          '"的所有社交关系数据吗？此操作不可撤销。',
        "清除关系数据",
        {
          confirmButtonText: "确认清除",
          cancelButtonText: "取消",
          type: "warning",
        },
      )
        .then(function () {
          // Second confirmation
          return ElementPlus.ElMessageBox.confirm(
            "请再次确认：清除后所有关系分析数据将被永久删除，需要重新分析才能恢复。",
            "二次确认",
            {
              confirmButtonText: "我确定要清除",
              cancelButtonText: "算了",
              type: "error",
            },
          );
        })
        .then(async function () {
          try {
            var resp = await fetch(
              "/api/social_relations/" +
                encodeURIComponent(self.currentGroupId) +
                "/clear",
              {
                method: "DELETE",
              },
            );
            var result = await resp.json();

            if (resp.ok) {
              ElementPlus.ElMessage.success("关系数据已清除");
              // Reload to show empty state
              await self.reloadCurrentGroup();
            } else {
              ElementPlus.ElMessage.error(
                (result && result.error) || "清除失败",
              );
            }
          } catch (e) {
            console.error("[SocialRelations] clearGroupRelations error:", e);
            ElementPlus.ElMessage.error(
              "清除请求失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {
          // User cancelled, do nothing
        });
    },

    /* ========== Navigation ========== */

    goBack() {
      this.stopAutoRefresh();
      this.disposeChart();
      this.disconnectResizeObserver();

      this.currentGroupId = null;
      this.currentGroupName = "";
      this.stats = {};
      this.members = [];
      this.relations = [];
      this.displayData = { nodes: [], links: [] };
      this.selectedUserId = "";
      this.memberSearch = "";
      this.graphLayout = "force";

      // Reload groups in case they changed
      this.loadGroups();
    },

    /* ========== Auto-Refresh ========== */

    startAutoRefresh() {
      this.stopAutoRefresh();
      var self = this;
      this.refreshTimer = setInterval(function () {
        self.reloadCurrentGroup();
      }, 30000);
    },

    stopAutoRefresh() {
      if (this.refreshTimer) {
        clearInterval(this.refreshTimer);
        this.refreshTimer = null;
      }
    },

    /* ========== ResizeObserver ========== */

    setupResizeObserver() {
      this.disconnectResizeObserver();
      var self = this;
      if (self.$refs.rootEl && typeof ResizeObserver !== "undefined") {
        self.resizeObserver = new ResizeObserver(function () {
          self.resizeChart();
        });
        self.resizeObserver.observe(self.$refs.rootEl);
      }
    },

    disconnectResizeObserver() {
      if (this.resizeObserver) {
        this.resizeObserver.disconnect();
        this.resizeObserver = null;
      }
    },
  },

  async mounted() {
    var self = this;

    // Register ECharts theme
    this.registerTheme();

    // Load group list
    await this.loadGroups();
    this.loading = false;
  },

  beforeUnmount() {
    // Cancel any in-flight requests
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }

    // Stop auto-refresh
    this.stopAutoRefresh();

    // Disconnect ResizeObserver
    this.disconnectResizeObserver();

    // Dispose chart
    this.disposeChart();
  },
};
