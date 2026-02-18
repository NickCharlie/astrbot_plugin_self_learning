/**
 * 学习状态 - Learning Status App
 * Shows current learning session info, learning history chart, and relearn trigger.
 */
window.AppLearningStatus = {
  props: { app: Object },
  template: `
    <div class="app-content">
      <!-- Top row: session info + history chart side by side -->
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">

        <!-- Current Session Info Card -->
        <div class="section-card" style="flex:1;min-width:260px;">
          <h3><i class="material-icons" style="font-size:16px;vertical-align:-3px;margin-right:4px;">info</i>当前学习会话</h3>
          <div class="info-row">
            <span class="info-label">会话ID</span>
            <span class="info-value" style="font-family:monospace;font-size:12px;">{{ session.session_id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">开始时间</span>
            <span class="info-value">{{ session.start_time }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">处理消息</span>
            <span class="info-value" style="font-weight:600;">{{ session.messages_processed }} 条</span>
          </div>
          <div class="info-row" style="border-bottom:none;">
            <span class="info-label">学习状态</span>
            <span class="info-value">
              <span :style="{
                display:'inline-block',
                padding:'2px 10px',
                borderRadius:'10px',
                fontSize:'11px',
                fontWeight:500,
                background: session.status === 'active' ? '#d1f2d1' : '#f2d1d1',
                color: session.status === 'active' ? '#0f5132' : '#842029'
              }">{{ session.status === 'active' ? '运行中' : '已停止' }}</span>
            </span>
          </div>
        </div>

        <!-- Learning History Chart Card -->
        <div class="section-card" style="flex:2;min-width:320px;">
          <h3><i class="material-icons" style="font-size:16px;vertical-align:-3px;margin-right:4px;">show_chart</i>学习历史</h3>
          <div ref="historyChart" class="chart-area" style="width:100%;height:250px;"></div>
        </div>

      </div>

      <!-- Relearn Action Card -->
      <div class="section-card">
        <h3><i class="material-icons" style="font-size:16px;vertical-align:-3px;margin-right:4px;">replay</i>重新学习</h3>
        <p style="font-size:12px;color:#86868b;margin:0 0 12px 0;">重新处理所有历史消息，重置学习状态并重新分析数据。此操作可能需要较长时间。</p>
        <div style="display:flex;align-items:center;gap:12px;">
          <el-button type="primary" :loading="relearnLoading" @click="triggerRelearn" size="small">
            <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:4px;" v-if="!relearnLoading">school</i>
            重新学习
          </el-button>
          <span v-if="relearnMessage" :style="{ fontSize:'12px', color: relearnSuccess ? '#0f5132' : '#842029' }">{{ relearnMessage }}</span>
        </div>
      </div>

      <!-- Social Links Footer -->
      <div class="social-links">
        <a class="qq-link" href="https://qm.qq.com/q/1021544792" target="_blank">QQ群: 1021544792</a>
        <a class="gh-link" href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank">GitHub</a>
      </div>

      <!-- Scoped styles -->
      <component :is="'style'">
        .app-content .info-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 9px 0;
          border-bottom: 1px solid #f0f0f0;
          font-size: 13px;
        }
        .app-content .info-label {
          color: #86868b;
          flex-shrink: 0;
          margin-right: 12px;
        }
        .app-content .info-value {
          color: #1d1d1f;
          text-align: right;
          word-break: break-all;
        }
      </component>
    </div>
  `,

  data() {
    return {
      session: {
        session_id: 'sess_' + Date.now(),
        start_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toLocaleString(),
        messages_processed: Math.floor(Math.random() * 100) + 50,
        status: 'active'
      },
      relearnLoading: false,
      relearnMessage: '',
      relearnSuccess: false,
      historyChart: null,
      resizeObserver: null
    };
  },

  methods: {
    /**
     * Register the ECharts material theme if not already registered.
     */
    ensureMaterialTheme() {
      if (!window.echarts || window._materialThemeRegistered) return;
      const materialTheme = {
        color: [
          '#1976d2', '#4caf50', '#ff9800', '#f44336',
          '#9c27b0', '#00bcd4', '#795548', '#607d8b'
        ],
        backgroundColor: 'transparent',
        textStyle: {
          fontFamily: 'Roboto, sans-serif',
          fontSize: 12,
          color: '#424242'
        },
        title: {
          textStyle: {
            fontFamily: 'Roboto, sans-serif',
            fontSize: 16,
            fontWeight: 500,
            color: '#212121'
          }
        },
        legend: {
          textStyle: {
            fontFamily: 'Roboto, sans-serif',
            fontSize: 12,
            color: '#757575'
          }
        },
        categoryAxis: {
          axisLine: { lineStyle: { color: '#e0e0e0' } },
          axisTick: { lineStyle: { color: '#e0e0e0' } },
          axisLabel: { color: '#757575' },
          splitLine: { lineStyle: { color: '#f5f5f5' } }
        },
        valueAxis: {
          axisLine: { lineStyle: { color: '#e0e0e0' } },
          axisTick: { lineStyle: { color: '#e0e0e0' } },
          axisLabel: { color: '#757575' },
          splitLine: { lineStyle: { color: '#f5f5f5' } }
        },
        grid: {
          borderColor: '#e0e0e0'
        }
      };
      window.echarts.registerTheme('material', materialTheme);
      window._materialThemeRegistered = true;
    },

    /**
     * Initialize the learning history chart from the trends API.
     */
    initHistoryChart() {
      const echarts = window.echarts;
      if (!echarts) {
        console.warn('[LearningStatus] ECharts not available');
        return;
      }

      this.ensureMaterialTheme();

      const chartDom = this.$refs.historyChart;
      if (!chartDom) return;

      this.historyChart = echarts.init(chartDom, 'material');

      fetch('/api/analytics/trends')
        .then(response => response.json())
        .then(data => {
          const hourlyData = data.hourly_trends || [];
          const hours = hourlyData.map(item => item.time);
          const rawMessages = hourlyData.map(item => item.raw_messages);
          const filteredMessages = hourlyData.map(item => item.filtered_messages);

          const option = {
            tooltip: {
              trigger: 'axis',
              axisPointer: { type: 'cross' }
            },
            legend: {
              data: ['原始消息', '筛选消息']
            },
            grid: {
              left: '3%',
              right: '4%',
              bottom: '3%',
              containLabel: true
            },
            xAxis: {
              type: 'category',
              data: hours.length > 0 ? hours : ['暂无数据'],
              boundaryGap: false
            },
            yAxis: {
              type: 'value'
            },
            series: [
              {
                name: '原始消息',
                type: 'line',
                data: rawMessages,
                smooth: true,
                itemStyle: { color: '#2196f3' },
                areaStyle: { opacity: 0.3 }
              },
              {
                name: '筛选消息',
                type: 'line',
                data: filteredMessages,
                smooth: true,
                itemStyle: { color: '#4caf50' },
                areaStyle: { opacity: 0.3 }
              }
            ]
          };

          this.historyChart.setOption(option);
        })
        .catch(error => {
          console.error('[LearningStatus] Failed to load trends:', error);
          // Show empty chart with time placeholders
          const hours = [];
          for (let i = 23; i >= 0; i--) {
            const hour = new Date(Date.now() - i * 60 * 60 * 1000);
            hours.push(hour.getHours() + ':00');
          }
          const option = {
            tooltip: { trigger: 'axis' },
            legend: { data: ['原始消息', '筛选消息'] },
            grid: {
              left: '3%',
              right: '4%',
              bottom: '3%',
              containLabel: true
            },
            xAxis: {
              type: 'category',
              data: hours,
              boundaryGap: false
            },
            yAxis: { type: 'value' },
            series: [
              { name: '原始消息', type: 'line', data: [], smooth: true, itemStyle: { color: '#2196f3' }, areaStyle: { opacity: 0.3 } },
              { name: '筛选消息', type: 'line', data: [], smooth: true, itemStyle: { color: '#4caf50' }, areaStyle: { opacity: 0.3 } }
            ]
          };
          this.historyChart.setOption(option);
        });

      // Set up ResizeObserver for responsive chart
      if (typeof ResizeObserver !== 'undefined') {
        this.resizeObserver = new ResizeObserver(() => {
          if (this.historyChart && !this.historyChart.isDisposed()) {
            this.historyChart.resize();
          }
        });
        this.resizeObserver.observe(chartDom);
      }
    },

    /**
     * Trigger relearn via POST /api/relearn.
     */
    async triggerRelearn() {
      this.relearnLoading = true;
      this.relearnMessage = '';
      try {
        const response = await fetch('/api/relearn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();

        if (response.ok && result.success) {
          this.relearnSuccess = true;
          this.relearnMessage = '重新学习已启动！将处理 ' + (result.total_messages || 0) + ' 条历史消息';
          if (typeof ElMessage !== 'undefined') {
            ElMessage.success('重新学习已启动！将处理 ' + (result.total_messages || 0) + ' 条历史消息');
          }
        } else {
          const errorMsg = result.error || '重新学习启动失败';
          this.relearnSuccess = false;
          this.relearnMessage = '启动失败: ' + errorMsg;
          if (typeof ElMessage !== 'undefined') {
            ElMessage.error('启动失败: ' + errorMsg);
          }
        }
      } catch (error) {
        console.error('[LearningStatus] Relearn request failed:', error);
        this.relearnSuccess = false;
        this.relearnMessage = '请求失败: ' + error.message;
        if (typeof ElMessage !== 'undefined') {
          ElMessage.error('请求失败: ' + error.message);
        }
      } finally {
        this.relearnLoading = false;
      }
    }
  },

  mounted() {
    // Load mock session data
    this.session = {
      session_id: 'sess_' + Date.now(),
      start_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toLocaleString(),
      messages_processed: Math.floor(Math.random() * 100) + 50,
      status: 'active'
    };

    // Init chart after DOM is ready
    this.$nextTick(() => {
      setTimeout(() => {
        this.initHistoryChart();
      }, 100);
    });
  },

  beforeUnmount() {
    // Clean up ResizeObserver
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    // Dispose ECharts instance
    if (this.historyChart && !this.historyChart.isDisposed()) {
      this.historyChart.dispose();
      this.historyChart = null;
    }
  }
};
