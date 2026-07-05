import type { EChartsOption } from 'echarts';
import { createMemo } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { formatCount, formatPercent } from '../../lib/format';
import { metric, object } from '../shared';
import { EChart } from '../../components/charts/EChart';
import { PageHeader } from '../../components/layout/PageHeader';
import { Panel, StatCard } from '../../components/ui';
import styles from './OverviewPage.module.scss';

export function OverviewPage() {
  const dashboard = useDashboard();
  const trendOption = createMemo<EChartsOption>(() => {
    const trends = object(dashboard.data.trends);
    const dailyMessages = object(trends.daily_messages);
    const recentBatches = Array.isArray(trends.recent_batches) ? trends.recent_batches as Record<string, unknown>[] : [];
    const labels = Object.keys(dailyMessages);
    const messages = labels.map((label) => Number(dailyMessages[label] ?? 0));
    const learnedByDay = new Map<string, number>();
    for (const batch of recentBatches) {
      const time = batch.created_at ?? batch.start_time;
      const date = time ? new Date(typeof time === 'number' && time < 1e12 ? time * 1000 : String(time)).toISOString().slice(0, 10) : '';
      if (date) learnedByDay.set(date, (learnedByDay.get(date) || 0) + Number(batch.processed_messages ?? batch.message_count ?? 0));
    }
    for (const date of learnedByDay.keys()) if (!labels.includes(date)) labels.push(date);
    labels.sort();
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 42, right: 24, top: 28, bottom: 34 },
      xAxis: { type: 'category', data: labels },
      yAxis: { type: 'value' },
      series: [
        { name: '消息', type: 'bar', data: labels.map((label) => messages[Object.keys(dailyMessages).indexOf(label)] || 0), itemStyle: { color: '#6476ff' } },
        { name: '学习处理', type: 'line', smooth: true, data: labels.map((label) => learnedByDay.get(label) || 0), lineStyle: { color: '#17b6a4' } },
      ],
    };
  });
  return (
    <div class="page">
      <PageHeader title="总览" description="学习系统的核心健康度、吞吐量和近期趋势。" icon="dashboard" />
      <div class="metrics-grid">
        <StatCard label="总消息数" icon="chat" value={formatCount(metric(dashboard.data, ['metrics.total_messages_collected']))} note="进入插件的数据总量" />
        <StatCard label="有效学习率" icon="school" tone="success" value={formatPercent(metric(dashboard.data, ['metrics.learning_efficiency', 'metrics.efficiency']) * (metric(dashboard.data, ['metrics.learning_efficiency', 'metrics.efficiency']) <= 1 ? 100 : 1))} />
        <StatCard label="过滤消息" icon="filter_alt" tone="warning" value={formatCount(metric(dashboard.data, ['metrics.filtered_messages', 'metrics.messages.filtered']))} />
        <StatCard label="系统内存" icon="memory" tone="warning" value={formatPercent(metric(dashboard.data, ['metrics.system_metrics.memory_percent']))} />
      </div>
      <div class="two-column">
        <Panel title="消息与学习趋势" hint="按后端聚合时间窗口展示">
          <EChart option={trendOption()} class="chart-lg" />
        </Panel>
        <Panel title="当前状态" hint="最近一次健康快照">
          <div class={styles['summary-copy']}>
            <span class="material-icons">insights</span>
            <h3>系统总体运行平稳</h3>
            <p>若某项指标为 0 或暂无曲线，通常表示对应数据尚未积累，而不是页面故障。</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
