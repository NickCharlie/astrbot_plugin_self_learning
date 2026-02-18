/**
 * 人格审查 - Persona Review App
 * Review queue for persona updates with tabs, filters, pagination,
 * batch operations, edit dialog, and diff highlighting.
 */
window.AppPersonaReview = {
  props: { app: Object },

  template: `
    <div class="app-content">
      <!-- Loading State -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载审查列表中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>

        <!-- ========== Header: Title + Stats ========== -->
        <div class="section-card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
          <h3 style="margin:0;display:flex;align-items:center;">
            <i class="material-icons" style="font-size:18px;margin-right:6px;color:#af52de;">rate_review</i>
            人格更新审查
          </h3>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;background:#fff3cd;color:#856404;font-weight:500;">
              待审查: {{ pendingCount }}
            </span>
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;background:#d1e7dd;color:#0f5132;font-weight:500;">
              已批准: {{ approvedCount }}
            </span>
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;background:#f8d7da;color:#842029;font-weight:500;">
              已拒绝: {{ rejectedCount }}
            </span>
            <el-button size="small" @click="refreshAll" :loading="refreshing">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;" v-if="!refreshing">refresh</i>
              刷新
            </el-button>
          </div>
        </div>

        <!-- ========== Tab Bar ========== -->
        <div class="tab-bar">
          <div class="tab-item" :class="{ active: activeTab === 'pending' }" @click="activeTab = 'pending'">
            待审查
          </div>
          <div class="tab-item" :class="{ active: activeTab === 'reviewed' }" @click="activeTab = 'reviewed'">
            审查历史
          </div>
        </div>

        <!-- ==================== Pending Tab ==================== -->
        <template v-if="activeTab === 'pending'">

          <!-- Filter Bar -->
          <div class="filter-bar">
            <el-select v-model="filters.type" placeholder="类型" size="small" style="width:130px;" clearable>
              <el-option label="全部类型" value="" />
              <el-option label="风格学习" value="style_learning" />
              <el-option label="人格学习" value="persona_learning" />
              <el-option label="常规更新" value="traditional" />
            </el-select>
            <el-select v-model="filters.group" placeholder="群组" size="small" style="width:140px;" clearable>
              <el-option label="全部群组" value="" />
              <el-option v-for="g in availableGroups" :key="g" :label="g" :value="g" />
            </el-select>
            <el-select v-model="filters.confidence" placeholder="置信度" size="small" style="width:130px;" clearable>
              <el-option label="全部置信度" value="" />
              <el-option label="高 (>=80%)" value="high" />
              <el-option label="中 (50-80%)" value="medium" />
              <el-option label="低 (<50%)" value="low" />
            </el-select>
            <el-select v-model="filters.time" placeholder="时间" size="small" style="width:130px;" clearable>
              <el-option label="全部时间" value="" />
              <el-option label="今天" value="today" />
              <el-option label="最近7天" value="7days" />
              <el-option label="最近30天" value="30days" />
            </el-select>
            <el-button size="small" @click="resetFilters">
              <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">filter_alt_off</i>
              重置
            </el-button>
          </div>

          <!-- Batch Operations -->
          <div v-if="filteredPendingUpdates.length > 0" style="display:flex;align-items:center;gap:10px;margin-bottom:10px;padding:0 4px;">
            <el-checkbox v-model="selectAll" @change="toggleSelectAll" style="margin-right:4px;">全选</el-checkbox>
            <template v-if="selectedIds.length > 0">
              <el-button size="small" type="success" @click="batchApprove">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">check_circle</i>
                批量批准 ({{ selectedIds.length }})
              </el-button>
              <el-button size="small" type="warning" @click="batchReject">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">cancel</i>
                批量拒绝 ({{ selectedIds.length }})
              </el-button>
              <el-button size="small" type="danger" @click="batchDelete">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">delete_sweep</i>
                批量删除 ({{ selectedIds.length }})
              </el-button>
            </template>
          </div>

          <!-- Review Items List -->
          <template v-if="paginatedUpdates.length > 0">
            <div v-for="item in paginatedUpdates" :key="item.id" class="review-item">
              <div style="display:flex;align-items:flex-start;gap:10px;">
                <el-checkbox
                  :model-value="selectedIds.indexOf(item.id) !== -1"
                  @change="toggleSelect(item.id, $event)"
                  style="margin-top:2px;" />
                <div style="flex:1;min-width:0;">
                  <!-- Badges row -->
                  <div class="badges" style="flex-wrap:wrap;">
                    <span class="badge" :class="getTypeBadgeClass(item.review_source)">{{ getTypeLabel(item.review_source) }}</span>
                    <span class="badge badge-id" style="font-family:monospace;">{{ shortId(item.id) }}</span>
                    <span v-if="item.group_id" class="badge" style="background:#e3f2fd;color:#1565c0;">{{ item.group_id }}</span>
                    <span class="badge" :style="getConfidenceStyle(item.confidence_score)">{{ formatConfidence(item.confidence_score) }}</span>
                    <span v-if="item.total_raw_messages" class="badge" style="background:#f0f0f0;color:#666;">
                      {{ item.messages_analyzed || 0 }}/{{ item.total_raw_messages }} 消息
                    </span>
                  </div>
                  <!-- Reason -->
                  <div style="font-size:12px;color:#1d1d1f;margin-bottom:6px;line-height:1.5;">{{ item.reason }}</div>
                  <!-- Timestamp -->
                  <div style="font-size:11px;color:#86868b;margin-bottom:8px;">{{ formatTime(item.timestamp) }}</div>
                  <!-- Content preview -->
                  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                    <div style="flex:1;min-width:200px;">
                      <div style="font-size:11px;color:#86868b;margin-bottom:4px;">原始内容</div>
                      <div style="font-size:12px;background:#f9f9fb;padding:8px;border-radius:6px;line-height:1.5;word-break:break-all;max-height:120px;overflow-y:auto;white-space:pre-wrap;">{{ getContentPreview(item, 'original') }}<span v-if="shouldShowToggle(item.original_content)" @click="toggleExpand(item.id, 'original')" style="color:#007aff;cursor:pointer;font-size:11px;margin-left:4px;">{{ isExpanded(item.id, 'original') ? '收起内容' : '展开完整内容' }}</span></div>
                    </div>
                    <div style="flex:1;min-width:200px;">
                      <div style="font-size:11px;color:#86868b;margin-bottom:4px;">建议内容</div>
                      <div style="font-size:12px;background:#f9f9fb;padding:8px;border-radius:6px;line-height:1.5;word-break:break-all;max-height:120px;overflow-y:auto;white-space:pre-wrap;" v-html="getProposedPreviewHtml(item)"></div>
                    </div>
                  </div>
                  <!-- Actions -->
                  <div class="action-row">
                    <el-button size="small" @click="openEditDialog(item)">
                      <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">edit</i>
                      编辑
                    </el-button>
                    <el-button size="small" type="success" @click="approveItem(item.id)">
                      <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">check</i>
                      批准
                    </el-button>
                    <el-button size="small" type="warning" @click="rejectItem(item.id)">
                      <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">close</i>
                      拒绝
                    </el-button>
                    <el-button size="small" type="danger" @click="deleteItem(item.id)">
                      <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">delete</i>
                      删除
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Empty State for Pending -->
          <div v-else class="empty-state">
            <i class="material-icons">inbox</i>
            <p>暂无待审查的人格更新</p>
          </div>

          <!-- Pagination -->
          <div v-if="totalPending > 0" class="pagination-bar">
            <span>显示 {{ paginationStart }}-{{ paginationEnd }} / 共 {{ totalPending }} 项</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <el-select v-model="pageSize" size="small" style="width:90px;" @change="onPageSizeChange">
                <el-option :label="'10条/页'" :value="10" />
                <el-option :label="'20条/页'" :value="20" />
                <el-option :label="'50条/页'" :value="50" />
                <el-option :label="'100条/页'" :value="100" />
              </el-select>
              <el-button size="small" :disabled="currentPage <= 1" @click="prevPage">上一页</el-button>
              <span style="font-size:12px;color:#1d1d1f;">{{ currentPage }} / {{ totalPages }}</span>
              <el-button size="small" :disabled="currentPage >= totalPages" @click="nextPage">下一页</el-button>
            </div>
          </div>

        </template>

        <!-- ==================== Reviewed Tab ==================== -->
        <template v-if="activeTab === 'reviewed'">

          <!-- Filter buttons -->
          <div style="display:flex;gap:8px;margin-bottom:12px;">
            <el-button size="small" :type="reviewedFilter === 'all' ? 'primary' : ''" @click="reviewedFilter = 'all'">全部</el-button>
            <el-button size="small" :type="reviewedFilter === 'approved' ? 'success' : ''" @click="reviewedFilter = 'approved'">已批准</el-button>
            <el-button size="small" :type="reviewedFilter === 'rejected' ? 'danger' : ''" @click="reviewedFilter = 'rejected'">已拒绝</el-button>
          </div>

          <!-- Reviewed Items List -->
          <template v-if="filteredReviewedUpdates.length > 0">
            <div v-for="item in filteredReviewedUpdates" :key="item.id" class="review-item">
              <div style="display:flex;align-items:flex-start;gap:10px;">
                <div style="flex:1;min-width:0;">
                  <!-- Badges row -->
                  <div class="badges" style="flex-wrap:wrap;">
                    <span class="badge" :class="getStatusBadgeClass(item.status)">{{ getStatusLabel(item.status) }}</span>
                    <span class="badge" :class="getTypeBadgeClass(item.review_source)">{{ getTypeLabel(item.review_source) }}</span>
                    <span class="badge badge-id" style="font-family:monospace;">{{ shortId(item.id) }}</span>
                    <span v-if="item.group_id" class="badge" style="background:#e3f2fd;color:#1565c0;">{{ item.group_id }}</span>
                    <span class="badge" :style="getConfidenceStyle(item.confidence_score)">{{ formatConfidence(item.confidence_score) }}</span>
                  </div>
                  <!-- Reason -->
                  <div style="font-size:12px;color:#1d1d1f;margin-bottom:6px;line-height:1.5;">{{ item.reason }}</div>
                  <!-- Timestamp -->
                  <div style="font-size:11px;color:#86868b;margin-bottom:8px;">{{ formatTime(item.timestamp) }}</div>
                  <!-- Content preview -->
                  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                    <div style="flex:1;min-width:200px;">
                      <div style="font-size:11px;color:#86868b;margin-bottom:4px;">原始内容</div>
                      <div style="font-size:12px;background:#f9f9fb;padding:8px;border-radius:6px;line-height:1.5;word-break:break-all;max-height:80px;overflow-y:auto;white-space:pre-wrap;">{{ truncateText(item.original_content, 200) }}</div>
                    </div>
                    <div style="flex:1;min-width:200px;">
                      <div style="font-size:11px;color:#86868b;margin-bottom:4px;">建议内容</div>
                      <div style="font-size:12px;background:#f9f9fb;padding:8px;border-radius:6px;line-height:1.5;word-break:break-all;max-height:80px;overflow-y:auto;white-space:pre-wrap;">{{ truncateText(item.proposed_content, 200) }}</div>
                    </div>
                  </div>
                  <!-- Actions -->
                  <div class="action-row">
                    <el-button size="small" @click="revertItem(item.id)">
                      <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">undo</i>
                      撤销审查
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Empty State for Reviewed -->
          <div v-else class="empty-state">
            <i class="material-icons">history</i>
            <p>暂无审查历史记录</p>
          </div>

        </template>

        <!-- ========== Edit Dialog ========== -->
        <el-dialog
          title="审查人格更新"
          v-model="editDialogVisible"
          width="680px"
          :close-on-click-modal="false"
          destroy-on-close>
          <div v-if="editItem" style="display:flex;flex-direction:column;gap:14px;">
            <!-- Info badges -->
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <span class="badge" :class="getTypeBadgeClass(editItem.review_source)" style="font-size:11px;padding:3px 10px;border-radius:10px;font-weight:500;">{{ getTypeLabel(editItem.review_source) }}</span>
              <span style="font-size:11px;padding:3px 10px;border-radius:10px;background:#f0f0f0;color:#666;font-family:monospace;font-weight:500;">{{ editItem.id }}</span>
              <span v-if="editItem.group_id" style="font-size:11px;padding:3px 10px;border-radius:10px;background:#e3f2fd;color:#1565c0;font-weight:500;">{{ editItem.group_id }}</span>
              <span style="font-size:11px;padding:3px 10px;border-radius:10px;font-weight:500;" :style="getConfidenceStyle(editItem.confidence_score)">{{ formatConfidence(editItem.confidence_score) }}</span>
            </div>
            <!-- Reason -->
            <div>
              <div style="font-size:12px;color:#86868b;margin-bottom:4px;">更新原因</div>
              <div style="font-size:13px;color:#1d1d1f;line-height:1.5;">{{ editItem.reason }}</div>
            </div>
            <!-- Timestamp -->
            <div style="font-size:12px;color:#86868b;">{{ formatTime(editItem.timestamp) }}</div>
            <!-- Original content (readonly) -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">原始内容 (只读)</label>
              <el-input
                :model-value="editItem.original_content"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 12 }"
                readonly
                resize="vertical" />
            </div>
            <!-- Proposed content (editable) -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">建议内容 (可编辑)</label>
              <el-input
                v-model="editForm.proposed_content"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 12 }"
                placeholder="编辑建议的人格更新内容..."
                resize="vertical" />
            </div>
            <!-- Features content -->
            <div v-if="editItem.features_content">
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">特征内容</label>
              <el-input
                :model-value="editItem.features_content"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                readonly
                resize="vertical" />
            </div>
            <!-- Review comment -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">审查备注</label>
              <el-input
                v-model="editForm.comment"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="可选: 添加审查备注..."
                resize="vertical" />
            </div>
          </div>

          <template #footer>
            <div style="display:flex;justify-content:flex-end;gap:8px;">
              <el-button @click="editDialogVisible = false">取消</el-button>
              <el-button type="warning" @click="submitEditReview('reject')" :loading="editSubmitting">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">close</i>
                拒绝
              </el-button>
              <el-button type="success" @click="submitEditReview('approve')" :loading="editSubmitting">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">check</i>
                批准
              </el-button>
            </div>
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

      // Data - current page only (server-side pagination)
      pageUpdates: [], // current page updates from server
      reviewedUpdates: [], // reviewed updates
      totalPending: 0, // total count from server

      // Tabs
      activeTab: "pending",

      // Filters (pending tab) - not used for server pagination currently
      filters: {
        type: "",
        group: "",
        confidence: "",
        time: "",
      },

      // Reviewed tab filter
      reviewedFilter: "all",

      // Pagination
      currentPage: 1,
      pageSize: 20,

      // Selection
      selectedIds: [],
      selectAll: false,

      // Expand state: { 'itemId_original': true, 'itemId_proposed': true }
      expandedMap: {},

      // Edit dialog
      editDialogVisible: false,
      editItem: null,
      editForm: {
        proposed_content: "",
        comment: "",
      },
      editSubmitting: false,

      // Refresh timer
      refreshTimer: null,
    };
  },

  computed: {
    /* ---------- Stats ---------- */
    pendingCount() {
      return this.totalPending;
    },
    approvedCount() {
      var count = 0;
      for (var i = 0; i < this.reviewedUpdates.length; i++) {
        if (this.reviewedUpdates[i].status === "approved") count++;
      }
      return count;
    },
    rejectedCount() {
      var count = 0;
      for (var i = 0; i < this.reviewedUpdates.length; i++) {
        if (this.reviewedUpdates[i].status === "rejected") count++;
      }
      return count;
    },

    /* ---------- Available groups (from data) ---------- */
    availableGroups() {
      var groups = {};
      for (var i = 0; i < this.pageUpdates.length; i++) {
        var g = this.pageUpdates[i].group_id;
        if (g) groups[g] = true;
      }
      return Object.keys(groups).sort();
    },

    /* ---------- Client-side filtered (current page only) ---------- */
    filteredPendingUpdates() {
      var self = this;
      var result = this.pageUpdates;

      // Type filter
      if (self.filters.type) {
        result = result.filter(function (u) {
          return u.review_source === self.filters.type;
        });
      }

      // Group filter
      if (self.filters.group) {
        result = result.filter(function (u) {
          return u.group_id === self.filters.group;
        });
      }

      // Confidence filter
      if (self.filters.confidence) {
        result = result.filter(function (u) {
          var score = u.confidence_score || 0;
          if (self.filters.confidence === "high") return score >= 0.8;
          if (self.filters.confidence === "medium")
            return score >= 0.5 && score < 0.8;
          if (self.filters.confidence === "low") return score < 0.5;
          return true;
        });
      }

      // Time filter
      if (self.filters.time) {
        var now = Date.now() / 1000;
        var cutoff = 0;
        if (self.filters.time === "today") {
          var todayStart = new Date();
          todayStart.setHours(0, 0, 0, 0);
          cutoff = todayStart.getTime() / 1000;
        } else if (self.filters.time === "7days") {
          cutoff = now - 7 * 86400;
        } else if (self.filters.time === "30days") {
          cutoff = now - 30 * 86400;
        }
        if (cutoff > 0) {
          result = result.filter(function (u) {
            return (u.timestamp || 0) >= cutoff;
          });
        }
      }

      return result;
    },

    /* ---------- Pagination (server-side) ---------- */
    totalPages() {
      return Math.max(1, Math.ceil(this.totalPending / this.pageSize));
    },
    paginatedUpdates() {
      return this.filteredPendingUpdates;
    },
    paginationStart() {
      if (this.totalPending === 0) return 0;
      return (this.currentPage - 1) * this.pageSize + 1;
    },
    paginationEnd() {
      return Math.min(this.currentPage * this.pageSize, this.totalPending);
    },

    /* ---------- Reviewed filtered ---------- */
    filteredReviewedUpdates() {
      var self = this;
      if (self.reviewedFilter === "all") return self.reviewedUpdates;
      return self.reviewedUpdates.filter(function (u) {
        return u.status === self.reviewedFilter;
      });
    },
  },

  watch: {
    filters: {
      handler: function () {
        this.selectedIds = [];
        this.selectAll = false;
      },
      deep: true,
    },
  },

  methods: {
    /* ========== Data Loading ========== */
    async loadPage(page) {
      var offset = (page - 1) * this.pageSize;
      try {
        var resp = await fetch(
          "/api/persona_updates?limit=" + this.pageSize + "&offset=" + offset,
          { credentials: "include" },
        );
        var data = await resp.json();
        if (data && data.success) {
          this.pageUpdates = data.updates || [];
          this.totalPending = data.total || 0;
        }
      } catch (e) {
        console.error("[PersonaReview] Failed to load page:", e);
        ElementPlus.ElMessage.error(
          "加载审查列表失败: " + (e.message || "网络错误"),
        );
      }
    },

    async loadReviewedUpdates() {
      try {
        var resp = await fetch("/api/persona_updates/reviewed", {
          credentials: "include",
        });
        var data = await resp.json();
        if (data && data.success) {
          this.reviewedUpdates = data.updates || [];
        }
      } catch (e) {
        console.error("[PersonaReview] Failed to load reviewed updates:", e);
      }
    },

    async refreshAll() {
      this.refreshing = true;
      try {
        await Promise.all([
          this.loadPage(this.currentPage),
          this.loadReviewedUpdates(),
        ]);
      } finally {
        this.refreshing = false;
      }
    },

    /* ========== Formatting & Display ========== */
    formatTime(timestamp) {
      if (!timestamp) return "未知时间";
      return new Date(timestamp * 1000).toLocaleString();
    },

    formatConfidence(score) {
      if (score == null) return "0.0%";
      return (score * 100).toFixed(1) + "%";
    },

    shortId(id) {
      if (!id && id !== 0) return "";
      var s = String(id);
      if (s.length <= 12) return s;
      return s.substring(0, 8) + "...";
    },

    truncateText(text, maxLen) {
      if (!text && text !== 0) return "";
      var s = String(text);
      if (s.length <= maxLen) return s;
      return s.substring(0, maxLen) + "...";
    },

    getTypeLabel(source) {
      if (source === "style_learning") return "风格学习";
      if (source === "persona_learning") return "人格学习";
      if (source === "traditional") return "常规更新";
      return source || "未知";
    },

    getTypeBadgeClass(source) {
      if (source === "style_learning") return "badge-style";
      if (source === "persona_learning") return "badge-persona";
      return "badge-general";
    },

    getStatusLabel(status) {
      if (status === "approved") return "已批准";
      if (status === "rejected") return "已拒绝";
      return "未知";
    },

    getStatusBadgeClass(status) {
      // Inline styles via computed, but we return a class and style
      if (status === "approved") return "badge-persona"; // green
      if (status === "rejected") return "badge-style"; // use red-ish inline
      return "badge-general";
    },

    getConfidenceStyle(score) {
      var pct = (score || 0) * 100;
      if (pct >= 80) return { background: "#d1e7dd", color: "#0f5132" };
      if (pct >= 50) return { background: "#fff3cd", color: "#856404" };
      return { background: "#f8d7da", color: "#842029" };
    },

    /* ========== Content Expansion ========== */
    shouldShowToggle(content) {
      return content && content.length > 200;
    },

    isExpanded(itemId, field) {
      return !!this.expandedMap[itemId + "_" + field];
    },

    toggleExpand(itemId, field) {
      var key = itemId + "_" + field;
      if (this.expandedMap[key]) {
        delete this.expandedMap[key];
      } else {
        this.expandedMap[key] = true;
      }
      // Trigger reactivity
      this.expandedMap = Object.assign({}, this.expandedMap);
    },

    getContentPreview(item, field) {
      var content =
        field === "original" ? item.original_content : item.proposed_content;
      if (!content) return "(空)";
      content = String(content);
      if (this.isExpanded(item.id, field) || content.length <= 200) {
        return content;
      }
      return content.substring(0, 200) + "...";
    },

    /* ========== Diff Highlighting ========== */
    getProposedPreviewHtml(item) {
      var proposed = item.proposed_content ? String(item.proposed_content) : "";
      var original = item.original_content ? String(item.original_content) : "";
      if (!proposed) return "(\u7A7A)";

      var displayText = proposed;
      var expanded = this.isExpanded(item.id, "proposed");
      var needsTruncation = proposed.length > 200 && !expanded;

      // Check if proposed starts with original (append case)
      if (
        original &&
        proposed.startsWith(original) &&
        proposed.length > original.length
      ) {
        var existingPart = original;
        var newPart = proposed.substring(original.length);

        if (needsTruncation) {
          // Truncate intelligently
          if (existingPart.length >= 200) {
            displayText =
              this.escapeHtml(existingPart.substring(0, 200)) + "...";
          } else {
            var remaining = 200 - existingPart.length;
            displayText =
              this.escapeHtml(existingPart) +
              '<span class="text-diff-new">' +
              this.escapeHtml(newPart.substring(0, remaining)) +
              "</span>...";
          }
        } else {
          displayText =
            this.escapeHtml(existingPart) +
            '<span class="text-diff-new">' +
            this.escapeHtml(newPart) +
            "</span>";
        }

        // Add toggle link
        if (this.shouldShowToggle(proposed)) {
          var toggleLabel = expanded ? "收起内容" : "展开完整内容";
          displayText +=
            '<span data-toggle-id="' +
            this.escapeHtml(item.id) +
            '" data-toggle-field="proposed" style="color:#007aff;cursor:pointer;font-size:11px;margin-left:4px;" onclick="this.dispatchEvent(new CustomEvent(\'toggle-expand\', {bubbles:true}))">' +
            toggleLabel +
            "</span>";
        }
        return displayText;
      }

      // Simple word-level diff for other cases
      if (original && proposed !== original) {
        var diffHtml = this.computeWordDiff(
          original,
          proposed,
          needsTruncation ? 200 : 0,
        );

        // Add toggle link
        if (this.shouldShowToggle(proposed)) {
          var toggleLabel2 = expanded ? "收起内容" : "展开完整内容";
          diffHtml +=
            '<span data-toggle-id="' +
            this.escapeHtml(item.id) +
            '" data-toggle-field="proposed" style="color:#007aff;cursor:pointer;font-size:11px;margin-left:4px;" onclick="this.dispatchEvent(new CustomEvent(\'toggle-expand\', {bubbles:true}))">' +
            toggleLabel2 +
            "</span>";
        }
        return diffHtml;
      }

      // No diff needed
      if (needsTruncation) {
        displayText = this.escapeHtml(proposed.substring(0, 200)) + "...";
      } else {
        displayText = this.escapeHtml(proposed);
      }

      if (this.shouldShowToggle(proposed)) {
        var toggleLabel3 = expanded ? "收起内容" : "展开完整内容";
        displayText +=
          '<span data-toggle-id="' +
          this.escapeHtml(item.id) +
          '" data-toggle-field="proposed" style="color:#007aff;cursor:pointer;font-size:11px;margin-left:4px;" onclick="this.dispatchEvent(new CustomEvent(\'toggle-expand\', {bubbles:true}))">' +
          toggleLabel3 +
          "</span>";
      }
      return displayText;
    },

    computeWordDiff(original, proposed, truncateAt) {
      var origWords = original.split(/(\s+)/);
      var propWords = proposed.split(/(\s+)/);
      var html = "";
      var charCount = 0;
      var truncated = false;
      var maxLen = propWords.length;

      for (var i = 0; i < maxLen; i++) {
        var word = propWords[i];
        if (truncateAt > 0 && charCount + word.length > truncateAt) {
          html +=
            this.escapeHtml(word.substring(0, truncateAt - charCount)) + "...";
          truncated = true;
          break;
        }

        if (i < origWords.length && origWords[i] === word) {
          html += this.escapeHtml(word);
        } else {
          html +=
            '<span class="text-diff-new">' + this.escapeHtml(word) + "</span>";
        }
        charCount += word.length;
      }

      return html;
    },

    escapeHtml(text) {
      if (!text && text !== 0) return "";
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    },

    /* ========== Selection ========== */
    toggleSelectAll(val) {
      if (val) {
        this.selectedIds = this.paginatedUpdates.map(function (u) {
          return u.id;
        });
      } else {
        this.selectedIds = [];
      }
    },

    toggleSelect(id, checked) {
      if (checked) {
        if (this.selectedIds.indexOf(id) === -1) {
          this.selectedIds.push(id);
        }
      } else {
        var idx = this.selectedIds.indexOf(id);
        if (idx !== -1) {
          this.selectedIds.splice(idx, 1);
        }
      }
      // Update selectAll state
      this.selectAll =
        this.paginatedUpdates.length > 0 &&
        this.selectedIds.length === this.paginatedUpdates.length;
    },

    /* ========== Filters ========== */
    resetFilters() {
      this.filters = { type: "", group: "", confidence: "", time: "" };
      this.currentPage = 1;
      this.loadPage(1);
    },

    onPageSizeChange() {
      this.currentPage = 1;
      this.loadPage(1);
    },

    prevPage() {
      if (this.currentPage > 1) {
        this.currentPage--;
        this.loadPage(this.currentPage);
      }
    },

    nextPage() {
      if (this.currentPage < this.totalPages) {
        this.currentPage++;
        this.loadPage(this.currentPage);
      }
    },

    /* ========== Single Item Actions ========== */
    async approveItem(id) {
      try {
        var resp = await fetch(
          "/api/persona_updates/" + encodeURIComponent(id) + "/review",
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "approve" }),
          },
        );
        var data = await resp.json();
        if (resp.ok) {
          ElementPlus.ElMessage.success("已批准更新");
          this.removeFromPending(id);
          this.loadReviewedUpdates();
        } else {
          ElementPlus.ElMessage.error((data && data.error) || "操作失败");
        }
      } catch (e) {
        console.error("[PersonaReview] Approve failed:", e);
        ElementPlus.ElMessage.error("批准失败: " + (e.message || "网络错误"));
      }
    },

    async rejectItem(id) {
      try {
        var resp = await fetch(
          "/api/persona_updates/" + encodeURIComponent(id) + "/review",
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "reject" }),
          },
        );
        var data = await resp.json();
        if (resp.ok) {
          ElementPlus.ElMessage.success("已拒绝更新");
          this.removeFromPending(id);
          this.loadReviewedUpdates();
        } else {
          ElementPlus.ElMessage.error((data && data.error) || "操作失败");
        }
      } catch (e) {
        console.error("[PersonaReview] Reject failed:", e);
        ElementPlus.ElMessage.error("拒绝失败: " + (e.message || "网络错误"));
      }
    },

    deleteItem(id) {
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        "确定要删除此更新吗？此操作不可撤销。",
        "删除更新",
        {
          confirmButtonText: "确认删除",
          cancelButtonText: "取消",
          type: "warning",
        },
      )
        .then(async function () {
          try {
            var resp = await fetch(
              "/api/persona_updates/" + encodeURIComponent(id) + "/delete",
              {
                method: "POST",
                credentials: "include",
              },
            );
            var data = await resp.json();
            if (resp.ok) {
              ElementPlus.ElMessage.success("已删除更新");
              self.removeFromPending(id);
            } else {
              ElementPlus.ElMessage.error((data && data.error) || "删除失败");
            }
          } catch (e) {
            console.error("[PersonaReview] Delete failed:", e);
            ElementPlus.ElMessage.error(
              "删除失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {
          // User cancelled
        });
    },

    async revertItem(id) {
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        "确定要撤销此审查决定吗？该更新将回到待审查状态。",
        "撤销审查",
        {
          confirmButtonText: "确认撤销",
          cancelButtonText: "取消",
          type: "info",
        },
      )
        .then(async function () {
          try {
            var resp = await fetch(
              "/api/persona_updates/" + encodeURIComponent(id) + "/revert",
              {
                method: "POST",
                credentials: "include",
              },
            );
            var data = await resp.json();
            if (resp.ok) {
              ElementPlus.ElMessage.success("已撤销审查");
              self.refreshAll();
            } else {
              ElementPlus.ElMessage.error((data && data.error) || "撤销失败");
            }
          } catch (e) {
            console.error("[PersonaReview] Revert failed:", e);
            ElementPlus.ElMessage.error(
              "撤销失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {
          // User cancelled
        });
    },

    /* ========== Batch Actions ========== */
    async batchApprove() {
      if (this.selectedIds.length === 0) return;
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        "确定要批量批准选中的 " + this.selectedIds.length + " 项更新吗？",
        "批量批准",
        {
          confirmButtonText: "确认批准",
          cancelButtonText: "取消",
          type: "info",
        },
      )
        .then(async function () {
          try {
            var resp = await fetch("/api/persona_updates/batch_review", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                update_ids: self.selectedIds.slice(),
                action: "approve",
                comment: "",
              }),
            });
            var data = await resp.json();
            if (resp.ok) {
              ElementPlus.ElMessage.success(
                "已批量批准 " + self.selectedIds.length + " 项更新",
              );
              self.removeManyFromPending(self.selectedIds.slice());
              self.selectedIds = [];
              self.selectAll = false;
              self.loadReviewedUpdates();
            } else {
              ElementPlus.ElMessage.error(
                (data && data.error) || "批量批准失败",
              );
            }
          } catch (e) {
            console.error("[PersonaReview] Batch approve failed:", e);
            ElementPlus.ElMessage.error(
              "批量批准失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {});
    },

    async batchReject() {
      if (this.selectedIds.length === 0) return;
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        "确定要批量拒绝选中的 " + this.selectedIds.length + " 项更新吗？",
        "批量拒绝",
        {
          confirmButtonText: "确认拒绝",
          cancelButtonText: "取消",
          type: "warning",
        },
      )
        .then(async function () {
          try {
            var resp = await fetch("/api/persona_updates/batch_review", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                update_ids: self.selectedIds.slice(),
                action: "reject",
                comment: "",
              }),
            });
            var data = await resp.json();
            if (resp.ok) {
              ElementPlus.ElMessage.success(
                "已批量拒绝 " + self.selectedIds.length + " 项更新",
              );
              self.removeManyFromPending(self.selectedIds.slice());
              self.selectedIds = [];
              self.selectAll = false;
              self.loadReviewedUpdates();
            } else {
              ElementPlus.ElMessage.error(
                (data && data.error) || "批量拒绝失败",
              );
            }
          } catch (e) {
            console.error("[PersonaReview] Batch reject failed:", e);
            ElementPlus.ElMessage.error(
              "批量拒绝失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {});
    },

    async batchDelete() {
      if (this.selectedIds.length === 0) return;
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        "确定要批量删除选中的 " +
          this.selectedIds.length +
          " 项更新吗？此操作不可撤销。",
        "批量删除",
        {
          confirmButtonText: "确认删除",
          cancelButtonText: "取消",
          type: "warning",
        },
      )
        .then(async function () {
          try {
            var resp = await fetch("/api/persona_updates/batch_delete", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ update_ids: self.selectedIds.slice() }),
            });
            var data = await resp.json();
            if (resp.ok) {
              ElementPlus.ElMessage.success(
                "已批量删除 " + self.selectedIds.length + " 项更新",
              );
              self.removeManyFromPending(self.selectedIds.slice());
              self.selectedIds = [];
              self.selectAll = false;
            } else {
              ElementPlus.ElMessage.error(
                (data && data.error) || "批量删除失败",
              );
            }
          } catch (e) {
            console.error("[PersonaReview] Batch delete failed:", e);
            ElementPlus.ElMessage.error(
              "批量删除失败: " + (e.message || "网络错误"),
            );
          }
        })
        .catch(function () {});
    },

    /* ========== Edit Dialog ========== */
    openEditDialog(item) {
      this.editItem = item;
      this.editForm = {
        proposed_content: item.proposed_content || "",
        comment: "",
      };
      this.editDialogVisible = true;
    },

    async submitEditReview(action) {
      if (!this.editItem) return;
      this.editSubmitting = true;
      try {
        var payload = { action: action };
        if (this.editForm.comment) {
          payload.comment = this.editForm.comment;
        }
        if (this.editForm.proposed_content !== this.editItem.proposed_content) {
          payload.modified_content = this.editForm.proposed_content;
        }

        var resp = await fetch(
          "/api/persona_updates/" +
            encodeURIComponent(this.editItem.id) +
            "/review",
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
        );
        var data = await resp.json();
        if (resp.ok) {
          ElementPlus.ElMessage.success(
            action === "approve" ? "已批准更新" : "已拒绝更新",
          );
          this.editDialogVisible = false;
          this.removeFromPending(this.editItem.id);
          this.loadReviewedUpdates();
        } else {
          ElementPlus.ElMessage.error((data && data.error) || "操作失败");
        }
      } catch (e) {
        console.error("[PersonaReview] Edit review failed:", e);
        ElementPlus.ElMessage.error("操作失败: " + (e.message || "网络错误"));
      } finally {
        this.editSubmitting = false;
      }
    },

    /* ========== Helpers ========== */
    removeFromPending(id) {
      this.pageUpdates = this.pageUpdates.filter(function (u) {
        return u.id !== id;
      });
      this.totalPending = Math.max(0, this.totalPending - 1);
      var idx = this.selectedIds.indexOf(id);
      if (idx !== -1) this.selectedIds.splice(idx, 1);
      // If current page is empty but there are more items, reload
      if (this.pageUpdates.length === 0 && this.totalPending > 0) {
        if (this.currentPage > 1) this.currentPage--;
        this.loadPage(this.currentPage);
      }
    },

    removeManyFromPending(ids) {
      var idSet = {};
      for (var j = 0; j < ids.length; j++) {
        idSet[ids[j]] = true;
      }
      this.pageUpdates = this.pageUpdates.filter(function (u) {
        return !idSet[u.id];
      });
      this.totalPending = Math.max(0, this.totalPending - ids.length);
      // If current page is empty but there are more items, reload
      if (this.pageUpdates.length === 0 && this.totalPending > 0) {
        if (this.currentPage > 1) this.currentPage--;
        this.loadPage(this.currentPage);
      }
    },
  },

  async mounted() {
    var self = this;

    // Initial load: first page + reviewed in parallel
    try {
      await Promise.all([this.loadPage(1), this.loadReviewedUpdates()]);
    } catch (e) {
      console.error("[PersonaReview] Initial load failed:", e);
    } finally {
      this.loading = false;
    }

    // Handle toggle-expand events from v-html content
    this.$el.addEventListener("toggle-expand", function (e) {
      var target = e.target;
      if (target && target.dataset) {
        var id = target.dataset.toggleId;
        var field = target.dataset.toggleField;
        if (id && field) {
          self.toggleExpand(id, field);
        }
      }
    });

    // Auto-refresh every 60 seconds
    this.refreshTimer = setInterval(function () {
      self.loadPage(self.currentPage);
      self.loadReviewedUpdates();
    }, 60000);
  },

  beforeUnmount() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  },
};
