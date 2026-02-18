/**
 * 黑话学习 - Jargon Learning App
 * Discovered jargon/slang terms with stats, filtering, search,
 * global sharing, and sync functionality.
 */
window.AppJargonLearning = {
  props: { app: Object },

  template: `
    <div class="app-content">
      <!-- Loading -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载数据中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>
        <!-- ========== Title bar ========== -->
        <div class="section-card" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <i class="material-icons" style="font-size:20px;color:#ff9500;">translate</i>
            <h3 style="margin:0;font-size:16px;font-weight:600;">黑话学习</h3>
          </div>
          <div style="display:flex;gap:8px;">
            <el-button size="small" @click="refreshAll" :loading="refreshing">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:2px;" v-if="!refreshing">refresh</i>
              刷新
            </el-button>
            <el-button size="small" type="primary" @click="showGlobalPanel = !showGlobalPanel">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:2px;">public</i>
              全局黑话管理
            </el-button>
          </div>
        </div>

        <!-- ========== Stat Cards ========== -->
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(stats.total_candidates) }}</div>
            <div class="stat-label">候选黑话数</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(stats.confirmed_jargon) }}</div>
            <div class="stat-label">已确认</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(stats.completed_inference) }}</div>
            <div class="stat-label">推理完成</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{{ formatNum(stats.total_occurrences) }}</div>
            <div class="stat-label">总出现次数</div>
          </div>
        </div>

        <!-- ========== Filter Bar ========== -->
        <div class="filter-bar">
          <el-select
            v-model="filterGroupId"
            placeholder="群组"
            clearable
            size="small"
            style="width:160px;"
            @change="handleFilterChange"
          >
            <el-option label="全部群组" value="" />
            <el-option
              v-for="g in groups"
              :key="g.group_id || g.id"
              :label="g.group_name || g.group_id || g.id"
              :value="String(g.group_id || g.id)"
            />
          </el-select>

          <el-select
            v-model="filterStatus"
            placeholder="状态"
            size="small"
            style="width:120px;"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="未确认" value="unconfirmed" />
          </el-select>

          <div style="flex:1;display:flex;gap:6px;min-width:180px;">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索黑话..."
              size="small"
              clearable
              @keyup.enter="handleSearch"
              @clear="handleFilterChange"
            />
            <el-button size="small" type="primary" @click="handleSearch">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:2px;">search</i>
              搜索
            </el-button>
          </div>
        </div>

        <!-- ========== Jargon List ========== -->
        <div v-if="jargonList.length === 0" class="empty-state">
          <i class="material-icons">sentiment_dissatisfied</i>
          <p>暂无黑话数据</p>
          <p style="font-size:11px;">请等待系统从群聊中自动发现黑话词汇</p>
        </div>

        <div v-else>
          <div
            class="section-card"
            v-for="item in jargonList"
            :key="item.id"
            style="margin-bottom:10px;"
          >
            <!-- Header row: term + badges -->
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px;">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <span style="font-size:15px;font-weight:700;color:#1d1d1f;">{{ item.term }}</span>
                <el-tag
                  size="small"
                  :type="item.is_confirmed ? 'success' : 'warning'"
                  effect="light"
                >{{ item.is_confirmed ? '已确认' : '候选' }}</el-tag>
                <el-tag
                  v-if="item.is_global"
                  size="small"
                  type="primary"
                  effect="light"
                >
                  <i class="material-icons" style="font-size:11px;vertical-align:-1px;margin-right:2px;">public</i>全局
                </el-tag>
                <el-tag
                  v-if="item.group_id"
                  size="small"
                  type="info"
                  effect="plain"
                >{{ item.group_id }}</el-tag>
              </div>
              <div style="display:flex;align-items:center;gap:4px;color:#86868b;font-size:11px;">
                <i class="material-icons" style="font-size:13px;">visibility</i>
                <span>{{ item.occurrences || 0 }} 次</span>
              </div>
            </div>

            <!-- Meaning -->
            <div v-if="item.meaning" style="margin-top:8px;font-size:13px;color:#555;line-height:1.6;">
              <strong style="color:#86868b;font-weight:500;">释义:</strong> {{ item.meaning }}
            </div>

            <!-- Context examples (collapsible) -->
            <div v-if="item.context_examples && item.context_examples.length > 0" style="margin-top:8px;">
              <div
                @click="toggleExamples(item.id)"
                style="cursor:pointer;display:flex;align-items:center;gap:4px;font-size:12px;color:#007aff;"
              >
                <i class="material-icons" style="font-size:14px;transition:transform 0.2s;"
                   :style="{ transform: expandedItems[item.id] ? 'rotate(90deg)' : 'rotate(0deg)' }"
                >chevron_right</i>
                上下文示例 ({{ item.context_examples.length }})
              </div>
              <div
                v-if="expandedItems[item.id]"
                style="margin-top:6px;padding:8px 12px;background:#f9f9fb;border-radius:6px;border:1px solid #f0f0f0;"
              >
                <div
                  v-for="(ex, idx) in item.context_examples"
                  :key="idx"
                  style="font-size:12px;color:#666;padding:3px 0;border-bottom:1px solid #f0f0f0;"
                  :style="{ borderBottom: idx === item.context_examples.length - 1 ? 'none' : '' }"
                >"{{ ex }}"</div>
              </div>
            </div>

            <!-- Action buttons -->
            <div class="action-row" style="margin-top:10px;padding-top:8px;border-top:1px solid #f0f0f0;">
              <el-button
                size="small"
                :type="item.is_global ? 'warning' : 'primary'"
                plain
                @click="toggleGlobal(item)"
              >
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">{{ item.is_global ? 'public_off' : 'public' }}</i>
                {{ item.is_global ? '取消全局' : '设为全局' }}
              </el-button>
              <el-button
                size="small"
                type="danger"
                plain
                @click="deleteJargon(item)"
              >
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">delete</i>
                删除
              </el-button>
            </div>
          </div>
        </div>

        <!-- ========== Global Jargon Panel ========== -->
        <div v-if="showGlobalPanel" class="section-card" style="border:2px solid #007aff;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h3 style="margin:0;display:flex;align-items:center;gap:6px;">
              <i class="material-icons" style="font-size:16px;color:#007aff;">public</i>
              全局黑话列表
            </h3>
            <div style="display:flex;gap:8px;">
              <el-button size="small" @click="loadGlobalJargon" :loading="globalLoading">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;" v-if="!globalLoading">refresh</i>
                刷新
              </el-button>
              <el-button size="small" type="success" @click="showSyncDialog = true">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">sync</i>
                同步到群组
              </el-button>
              <el-button size="small" @click="showGlobalPanel = false">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;">close</i>
              </el-button>
            </div>
          </div>

          <div v-if="globalLoading" class="loading-center">
            <i class="material-icons" style="font-size:20px;animation:spin 1s linear infinite;">refresh</i>
          </div>

          <div v-else-if="globalJargonList.length === 0" class="empty-state" style="padding:20px;">
            <p style="margin:0;font-size:12px;">暂无全局共享黑话</p>
          </div>

          <div v-else style="max-height:300px;overflow-y:auto;">
            <div
              v-for="gItem in globalJargonList"
              :key="gItem.id"
              style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #f0f0f0;"
            >
              <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                  <span style="font-weight:600;font-size:13px;">{{ gItem.term }}</span>
                  <el-tag size="small" type="success" effect="light" v-if="gItem.is_confirmed">已确认</el-tag>
                  <el-tag size="small" type="info" effect="plain" v-if="gItem.group_id">{{ gItem.group_id }}</el-tag>
                </div>
                <div v-if="gItem.meaning" style="font-size:11px;color:#86868b;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  {{ gItem.meaning }}
                </div>
              </div>
              <el-button
                size="small"
                type="danger"
                plain
                @click="removeFromGlobal(gItem)"
                style="margin-left:8px;flex-shrink:0;"
              >
                <i class="material-icons" style="font-size:12px;vertical-align:-2px;">remove_circle</i>
              </el-button>
            </div>
          </div>
        </div>

        <!-- ========== Sync Dialog ========== -->
        <el-dialog
          v-model="showSyncDialog"
          title="同步全局黑话到群组"
          width="400px"
          :close-on-click-modal="false"
        >
          <div style="margin-bottom:16px;">
            <p style="font-size:13px;color:#555;margin:0 0 12px;">
              将所有全局共享的黑话词汇同步到指定群组，使该群组可以识别和使用这些黑话。
            </p>
            <el-select
              v-model="syncTargetGroupId"
              placeholder="选择目标群组"
              style="width:100%;"
            >
              <el-option
                v-for="g in groups"
                :key="g.group_id || g.id"
                :label="g.group_name || g.group_id || g.id"
                :value="String(g.group_id || g.id)"
              />
            </el-select>
          </div>
          <template #footer>
            <el-button @click="showSyncDialog = false">取消</el-button>
            <el-button
              type="primary"
              @click="syncToGroup"
              :loading="syncing"
              :disabled="!syncTargetGroupId"
            >
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:2px;" v-if="!syncing">sync</i>
              确认同步
            </el-button>
          </template>
        </el-dialog>

        <!-- ========== Social Links Footer ========== -->
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
      refreshing: false,
      groups: [],
      stats: {
        total_candidates: 0,
        confirmed_jargon: 0,
        completed_inference: 0,
        total_occurrences: 0,
      },
      jargonList: [],
      // Filters
      filterGroupId: "",
      filterStatus: "",
      searchKeyword: "",
      // Expanded context examples
      expandedItems: {},
      // Global panel
      showGlobalPanel: false,
      globalJargonList: [],
      globalLoading: false,
      // Sync dialog
      showSyncDialog: false,
      syncTargetGroupId: "",
      syncing: false,
    };
  },

  methods: {
    /* ---------- Utility ---------- */
    formatNum(n) {
      if (n == null) return "0";
      n = Number(n);
      if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
      if (n >= 1000) return (n / 1000).toFixed(1) + "K";
      return String(n);
    },

    toggleExamples(id) {
      this.expandedItems = Object.assign({}, this.expandedItems, {
        [id]: !this.expandedItems[id],
      });
    },

    /* ---------- Data loading ---------- */
    async loadGroups() {
      try {
        var resp = await fetch("/api/jargon/groups", {
          credentials: "include",
        });
        if (resp.ok) {
          var data = await resp.json();
          this.groups = Array.isArray(data) ? data : data.groups || [];
        }
      } catch (e) {
        console.error("[JargonLearning] loadGroups error:", e);
      }
    },

    async loadStats() {
      try {
        var url = "/api/jargon/stats";
        if (this.filterGroupId) {
          url += "?group_id=" + encodeURIComponent(this.filterGroupId);
        }
        var resp = await fetch(url, { credentials: "include" });
        if (resp.ok) {
          var data = await resp.json();
          this.stats = {
            total_candidates: data.total_candidates || 0,
            confirmed_jargon: data.confirmed_jargon || 0,
            completed_inference: data.completed_inference || 0,
            total_occurrences: data.total_occurrences || 0,
          };
        }
      } catch (e) {
        console.error("[JargonLearning] loadStats error:", e);
      }
    },

    async loadJargonList() {
      try {
        var params = [];
        if (this.filterGroupId)
          params.push("group_id=" + encodeURIComponent(this.filterGroupId));
        if (this.filterStatus === "confirmed") params.push("confirmed=true");
        else if (this.filterStatus === "unconfirmed")
          params.push("confirmed=false");
        if (this.searchKeyword)
          params.push("keyword=" + encodeURIComponent(this.searchKeyword));

        var url =
          "/api/jargon/list" +
          (params.length > 0 ? "?" + params.join("&") : "");
        var resp = await fetch(url, { credentials: "include" });
        if (resp.ok) {
          var data = await resp.json();
          this.jargonList = data.jargon_list || data || [];
        }
      } catch (e) {
        console.error("[JargonLearning] loadJargonList error:", e);
        this.jargonList = [];
      }
    },

    async loadGlobalJargon() {
      this.globalLoading = true;
      try {
        var resp = await fetch("/api/jargon/global?limit=50", {
          credentials: "include",
        });
        if (resp.ok) {
          var data = await resp.json();
          this.globalJargonList = data.jargon_list || data || [];
        }
      } catch (e) {
        console.error("[JargonLearning] loadGlobalJargon error:", e);
      } finally {
        this.globalLoading = false;
      }
    },

    /* ---------- Filter & Search ---------- */
    async handleFilterChange() {
      await Promise.all([this.loadStats(), this.loadJargonList()]);
    },

    async handleSearch() {
      if (!this.searchKeyword.trim()) {
        await this.handleFilterChange();
        return;
      }
      try {
        var params = [
          "keyword=" + encodeURIComponent(this.searchKeyword.trim()),
        ];
        if (this.filterGroupId)
          params.push("group_id=" + encodeURIComponent(this.filterGroupId));
        if (this.filterStatus === "confirmed")
          params.push("confirmed_only=true");

        var url = "/api/jargon/search?" + params.join("&");
        var resp = await fetch(url, { credentials: "include" });
        if (resp.ok) {
          var data = await resp.json();
          this.jargonList = data.jargon_list || data || [];
        }
      } catch (e) {
        console.error("[JargonLearning] handleSearch error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("搜索失败: " + e.message);
        }
      }
    },

    /* ---------- Actions ---------- */
    async toggleGlobal(item) {
      try {
        var resp = await fetch("/api/jargon/" + item.id + "/toggle_global", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        if (resp.ok) {
          item.is_global = !item.is_global;
          if (typeof ElMessage !== "undefined") {
            ElMessage.success(
              item.is_global ? "已设为全局共享" : "已取消全局共享",
            );
          }
          // Refresh global list if panel is open
          if (this.showGlobalPanel) {
            this.loadGlobalJargon();
          }
        } else {
          var err = await resp.json().catch(function () {
            return {};
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.error(
              "操作失败: " + (err.error || err.message || "未知错误"),
            );
          }
        }
      } catch (e) {
        console.error("[JargonLearning] toggleGlobal error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("操作失败: " + e.message);
        }
      }
    },

    async deleteJargon(item) {
      try {
        if (typeof ElMessageBox !== "undefined") {
          await ElMessageBox.confirm(
            '确定要删除黑话 "' + item.term + '" 吗？此操作不可撤销。',
            "删除确认",
            {
              confirmButtonText: "确认删除",
              cancelButtonText: "取消",
              type: "warning",
            },
          );
        }
      } catch (e) {
        // User cancelled
        return;
      }

      try {
        var resp = await fetch("/api/jargon/" + item.id, {
          method: "DELETE",
          credentials: "include",
        });
        if (resp.ok) {
          // Remove from local list
          this.jargonList = this.jargonList.filter(function (j) {
            return j.id !== item.id;
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.success('已删除 "' + item.term + '"');
          }
          // Refresh stats
          this.loadStats();
        } else {
          var err = await resp.json().catch(function () {
            return {};
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.error(
              "删除失败: " + (err.error || err.message || "未知错误"),
            );
          }
        }
      } catch (e) {
        console.error("[JargonLearning] deleteJargon error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("删除失败: " + e.message);
        }
      }
    },

    async removeFromGlobal(item) {
      try {
        var resp = await fetch("/api/jargon/" + item.id + "/set_global", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_global: false }),
        });
        if (resp.ok) {
          // Remove from global list
          this.globalJargonList = this.globalJargonList.filter(function (j) {
            return j.id !== item.id;
          });
          // Update main list item if visible
          var mainItem = this.jargonList.find(function (j) {
            return j.id === item.id;
          });
          if (mainItem) mainItem.is_global = false;
          if (typeof ElMessage !== "undefined") {
            ElMessage.success('已从全局列表移除 "' + item.term + '"');
          }
        } else {
          var err = await resp.json().catch(function () {
            return {};
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.error(
              "操作失败: " + (err.error || err.message || "未知错误"),
            );
          }
        }
      } catch (e) {
        console.error("[JargonLearning] removeFromGlobal error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("操作失败: " + e.message);
        }
      }
    },

    async syncToGroup() {
      if (!this.syncTargetGroupId) return;
      this.syncing = true;
      try {
        var resp = await fetch("/api/jargon/sync_to_group", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ group_id: this.syncTargetGroupId }),
        });
        if (resp.ok) {
          var data = await resp.json().catch(function () {
            return {};
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.success(
              "同步成功" +
                (data.synced_count != null
                  ? "，共同步 " + data.synced_count + " 条黑话"
                  : ""),
            );
          }
          this.showSyncDialog = false;
          this.syncTargetGroupId = "";
          // Refresh list to show updated data
          this.loadJargonList();
        } else {
          var err = await resp.json().catch(function () {
            return {};
          });
          if (typeof ElMessage !== "undefined") {
            ElMessage.error(
              "同步失败: " + (err.error || err.message || "未知错误"),
            );
          }
        }
      } catch (e) {
        console.error("[JargonLearning] syncToGroup error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("同步失败: " + e.message);
        }
      } finally {
        this.syncing = false;
      }
    },

    /* ---------- Refresh all ---------- */
    async refreshAll() {
      this.refreshing = true;
      try {
        await Promise.all([
          this.loadGroups(),
          this.loadStats(),
          this.loadJargonList(),
        ]);
        if (this.showGlobalPanel) {
          await this.loadGlobalJargon();
        }
        if (typeof ElMessage !== "undefined") {
          ElMessage.success("数据已刷新");
        }
      } catch (e) {
        console.error("[JargonLearning] refreshAll error:", e);
      } finally {
        this.refreshing = false;
      }
    },
  },

  watch: {
    showGlobalPanel(val) {
      if (val) {
        this.loadGlobalJargon();
      }
    },
  },

  async mounted() {
    try {
      await Promise.all([
        this.loadGroups(),
        this.loadStats(),
        this.loadJargonList(),
      ]);
    } catch (e) {
      console.error("[JargonLearning] mounted error:", e);
    } finally {
      this.loading = false;
    }
  },

  beforeUnmount() {
    // Clean up any timers
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
    // Clean up any observers
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  },
};
