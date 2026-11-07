import type { DashboardSnapshot, IntegrationPayload, PageId, Tone } from '../../types/dashboard';
import { formatCount, formatScore } from '../../lib/format';
import { intelligenceScore, metric, object, reviewBacklog } from '../shared';

export type Insight = { title: string; detail: string; tone: Tone; page: PageId; value: number };

export const insightLevel = (tone: Tone): string =>
  tone === 'danger' ? '高' : tone === 'warning' ? '中' : '提示';

// AI 巡检规则集。内嵌插件页 pages/dashboard/app.js 的 buildInsights 使用同一组规则、
// 顺序与文案（改动需两端同步）。
export function buildInsights(data: DashboardSnapshot, integrations?: IntegrationPayload | null): Insight[] {
  const rows: Insight[] = [];
  const runtime = object(object(data.health).runtime);
  if (runtime.database_degraded === true) {
    const error = runtime.database_start_error;
    rows.push({
      title: '数据库处于降级状态',
      detail: error ? String(error) : '数据库服务未完整启动。',
      tone: 'danger', page: 'monitoring', value: 1,
    });
  }
  // 与首页待办同源：读待审接口分页 total，已驳回不再计入
  const backlog = reviewBacklog(data).total;
  if (backlog > 0) rows.push({ title: '审查队列存在积压', detail: `当前约 ${formatCount(backlog)} 条记录等待处理。`, tone: backlog > 20 ? 'danger' : 'warning', page: 'reviews', value: backlog });
  const filtered = metric(data, ['metrics.filtered_messages', 'metrics.messages.filtered']);
  if (filtered > 0) rows.push({ title: '过滤链路持续工作', detail: `${formatCount(filtered)} 条消息因质量或规则未进入学习。`, tone: 'default', page: 'monitoring', value: filtered });
  const failures = Object.values(object(object(data.health).checks))
    .filter((item) => object(item).status && object(item).status !== 'healthy').length;
  if (failures > 0) rows.push({ title: '健康检查发现异常', detail: `${formatCount(failures)} 项检查未处于健康状态。`, tone: 'danger', page: 'monitoring', value: failures });
  const { score } = intelligenceScore(data);
  if (score > 0 && score < 60) rows.push({ title: '智能评分偏低', detail: `综合评分 ${formatScore(score)}，建议查看表达样本和学习批次。`, tone: 'warning', page: 'monitoring', value: score });
  const delegation = object(object(integrations).delegation);
  if (delegation.memory_delegated || delegation.reply_delegated) {
    rows.push({
      title: '伴随插件委托已启用',
      detail: `记忆委托: ${delegation.memory_delegated ? '是' : '否'}，回复委托: ${delegation.reply_delegated ? '是' : '否'}。`,
      tone: 'default', page: 'integrations',
      value: Number(Boolean(delegation.memory_delegated)) + Number(Boolean(delegation.reply_delegated)),
    });
  }
  for (const [name, message] of Object.entries(object(data.load_errors))) {
    rows.push({ title: `模块 ${name} 读取失败`, detail: String(message), tone: 'warning', page: 'monitoring', value: 1 });
  }
  if (!rows.length) rows.push({ title: '暂未发现需要立即处理的问题', detail: '当前快照没有明显积压或健康告警。', tone: 'success', page: 'overview', value: 0 });
  return rows;
}
