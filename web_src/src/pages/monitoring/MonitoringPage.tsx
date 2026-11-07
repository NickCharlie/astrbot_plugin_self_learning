import { For } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { detailText, intelligenceScore, object } from '../shared';
import { formatCount, formatScore, textOrDash } from '../../lib/format';
import { Badge, Panel, ProgressBar, StatCard } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './MonitoringPage.module.scss';

export function MonitoringPage() {
  const dashboard = useDashboard();
  const health = () => object(dashboard.data.health);
  const functions = () => object(dashboard.data.functions);
  const functionRows = () => Array.isArray(functions().functions)
    ? functions().functions as Record<string, unknown>[]
    : [];
  const llmRows = (): Record<string, unknown>[] => {
    const metrics = object(dashboard.data.metrics);
    const source = metrics.llm_call_breakdown ?? metrics.llm_calls ?? metrics.filter_model_summary ?? {};
    return Array.isArray(source)
      ? source as Record<string, unknown>[]
      : Object.entries(object(source)).map(([provider, calls]) =>
        (typeof calls === 'object' ? { provider, ...object(calls) } : { provider, calls }) as Record<string, unknown>);
  };
  const llmTotal = () => object(object(dashboard.data.metrics).llm_call_summary).total_calls;
  const healthRows = (): Record<string, unknown>[] => {
    const source = health().checks ?? health().items ?? health();
    return Array.isArray(source) ? source as Record<string, unknown>[] : Object.entries(object(source)).map(([name, value]) => ({ name, ...(object(value)) } as Record<string, unknown>));
  };
  const score = () => intelligenceScore(dashboard.data);
  return (
    <div class="page">
      <PageHeader title="运行监控" description="检查核心能力、后台任务与模型调用的运行状态。" icon="monitor_heart" />
      <div class="metrics-grid">
        <StatCard label="健康检查" value={formatCount(healthRows().length)} icon="health_and_safety" />
        <StatCard label="函数追踪" value={formatCount(functionRows().length)} icon="functions" note={functions().trace_enabled ? '已启用' : '未启用'} />
        <StatCard label="总体状态" value={textOrDash(health().overall ?? health().status)} tone={health().overall === 'healthy' ? 'success' : 'warning'} icon="monitor_heart" />
        <StatCard label="综合评分" value={formatScore(score().score)} icon="insights"
          note={score().dimensions ? `已有 ${formatCount(score().dimensions)} 个维度参与评估。` : '智能指标服务暂未产生维度数据。'} />
      </div>
      <div class="two-column">
        <Panel title="系统健康" hint="后端健康检查结果">
          <div class="check-list">
            <For each={healthRows()} fallback={<p class="footer-note">暂无健康检查数据</p>}>{(item) =>
              <div class="check-row">
                <div><strong>{textOrDash(item.name ?? item.key)}</strong><small>{detailText(item.detail ?? item.message)}</small></div>
                <Badge tone={item.status === 'healthy' || item.ok === true ? 'success' : item.status === 'unhealthy' ? 'danger' : 'warning'}>{textOrDash(item.status ?? (item.ok ? 'healthy' : 'unknown'))}</Badge>
              </div>
            }</For>
          </div>
        </Panel>
        <Panel title="监控热点" hint="可量化的函数与调用指标">
          <div class={styles['progress-list']}>
            <For each={functionRows()} fallback={<p class="footer-note">当前没有函数追踪样本；可在配置中开启 trace。</p>}>{(item) =>
              <ProgressBar label={textOrDash(item.name ?? item.function)} value={Math.min(100, Number(item.avg_ms ?? item.total_ms ?? item.calls) || 0)} />
            }</For>
          </div>
        </Panel>
      </div>
      <Panel title="模型调用" hint="按 Provider 汇总当前统计窗口" actions={<Badge>{`${formatCount(llmTotal())} 次调用`}</Badge>}>
        <div class="data-list">
          <For each={llmRows()} fallback={<p class="footer-note">暂无模型调用统计</p>}>{(item) =>
            <div class="check-row">
              <div>
                <strong>{textOrDash(item.provider_label ?? item.provider_type ?? item.provider ?? item.name ?? item.model)}</strong>
                <small>{`平均 ${formatCount(item.avg_response_time_ms)}ms · 失败 ${formatCount(item.error_count ?? item.errors)}`}</small>
              </div>
              <Badge tone={item.is_abnormal === true || item.abnormal === true ? 'danger' : 'default'}>{formatCount(item.total_calls ?? item.calls ?? item.count)}</Badge>
            </div>
          }</For>
        </div>
      </Panel>
    </div>
  );
}
