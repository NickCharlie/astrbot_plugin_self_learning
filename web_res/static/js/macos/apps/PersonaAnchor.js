/**
 * Persona Anchor App
 * Display Persona Anchor metrics, config, and recent injection history.
 * Auto-refreshes every 10 seconds.
 */
window.AppPersonaAnchor = {
  props: { app: Object },

  template: `
    <div class="app-content" ref="rootEl">
      <!-- Loading -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载数据中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>
        <!-- Not enabled -->
        <div v-if="!metrics.enabled" class="empty-state">
          <i class="material-icons">anchor</i>
          <p>Persona Anchor 未启用</p>
          <p style="font-size:11px;color:#86868b;">
            请在插件配置中开启「启用 Persona Anchor 注入」后重启插件。
          </p>
        </div>

        <template v-else>
          <!-- ========== Config Bar ========== -->
          <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
            <el-tag size="small" type="success">已启用</el-tag>
            <el-tag size="small">Bot 样本: {{ config.persona_anchor_bot_k }}</el-tag>
            <el-tag size="small">用户样本: {{ config.persona_anchor_user_k }}</el-tag>
            <el-tag size="small">候选池: {{ config.persona_anchor_pool }}</el-tag>
            <el-tag size="small">最小样本: {{ config.persona_anchor_min_samples }}</el-tag>
          </div>

          <!-- ========== Metrics Cards ========== -->
          <div class="stat-grid">
            <div class="stat-card">
              <div class="stat-number">{{ metrics.total_calls }}</div>
              <div class="stat-label">总调用次数</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ metrics.successful_injections }}</div>
              <div class="stat-label">成功注入</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ metrics.injection_rate }}%</div>
              <div class="stat-label">注入率</div>
            </div>
            <div class="stat-card">
              <div class="stat-number">{{ metrics.avg_relevance_score }}</div>
              <div class="stat-label">平均相关性</div>
            </div>
          </div>

          <!-- ========== Skip Reasons ========== -->
          <div style="margin-top:16px;">
            <h4 style="margin:0 0 8px 0;font-size:14px;color:var(--text-primary);">跳过原因分布</h4>
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
              <el-tag size="small" type="info">配置禁用: {{ metrics.skips_disabled }}</el-tag>
              <el-tag size="small" type="warning">样本不足: {{ metrics.skips_insufficient }}</el-tag>
              <el-tag size="small" type="danger">无匹配: {{ metrics.skips_no_scored }}</el-tag>
            </div>
          </div>

          <!-- ========== Pool Stats ========== -->
          <div style="margin-top:16px;">
            <h4 style="margin:0 0 8px 0;font-size:14px;color:var(--text-primary);">平均池大小</h4>
            <div class="stat-grid" style="grid-template-columns:repeat(2,1fr);">
              <div class="stat-card">
                <div class="stat-number">{{ metrics.avg_bot_pool_size }}</div>
                <div class="stat-label">Bot 候选池</div>
              </div>
              <div class="stat-card">
                <div class="stat-number">{{ metrics.avg_user_pool_size }}</div>
                <div class="stat-label">用户候选池</div>
              </div>
            </div>
          </div>

          <!-- ========== Recent History ========== -->
          <div style="margin-top:16px;">
            <h4 style="margin:0 0 8px 0;font-size:14px;color:var(--text-primary);">最近注入记录（最近 20 条）</h4>
            <el-table :data="metrics.recent_history" size="small" style="width:100%">
              <el-table-column prop="ts" label="时间" width="160">
                <template #default="scope">
                  {{ formatTime(scope.row.ts) }}
                </template>
              </el-table-column>
              <el-table-column label="结果" width="80">
                <template #default="scope">
                  <el-tag size="small" :type="scope.row.success ? 'success' : 'info'">
                    {{ scope.row.success ? '注入' : '跳过' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="bot_pool_size" label="Bot池" width="80" />
              <el-table-column prop="user_pool_size" label="用户池" width="80" />
              <el-table-column prop="score" label="相关性" width="90" />
            </el-table>
            <div v-if="metrics.recent_history.length === 0" style="text-align:center;padding:20px;color:#86868b;font-size:13px;">
              暂无注入记录，在群里多发几条消息触发 LLM 后即可看到数据。
            </div>
          </div>
        </template>
      </template>
    </div>
  `,

  data() {
    return {
      loading: true,
      metrics: {
        enabled: false,
        total_calls: 0,
        successful_injections: 0,
        injection_rate: 0,
        skips_disabled: 0,
        skips_insufficient: 0,
        skips_no_scored: 0,
        avg_bot_pool_size: 0,
        avg_user_pool_size: 0,
        avg_relevance_score: 0,
        recent_history: [],
      },
      config: {
        enable_persona_anchor: false,
        persona_anchor_bot_k: 3,
        persona_anchor_user_k: 2,
        persona_anchor_pool: 30,
        persona_anchor_min_samples: 3,
      },
      refreshTimer: null,
    };
  },

  mounted() {
    this.loadData();
    this.refreshTimer = setInterval(() => this.loadData(), 10000);
  },

  beforeUnmount() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
    }
  },

  methods: {
    async loadData() {
      try {
        const [metricsRes, configRes] = await Promise.all([
          fetch("/api/anchor/metrics").then(function (r) { return r.json(); }),
          fetch("/api/anchor/config").then(function (r) { return r.json(); }),
        ]);

        if (metricsRes) {
          this.metrics = metricsRes;
        }
        if (configRes) {
          this.config = configRes;
        }
      } catch (e) {
        console.error("[PersonaAnchor] loadData failed:", e);
      } finally {
        this.loading = false;
      }
    },

    formatTime(ts) {
      if (!ts) return "-";
      const d = new Date(ts * 1000);
      return d.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    },
  },
};
