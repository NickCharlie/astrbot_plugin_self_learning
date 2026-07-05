import { createMemo, For } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import type { PageId, Tone } from '../../types/dashboard';
import { formatCount } from '../../lib/format';
import { metric, object } from '../shared';
import { Badge, Button, Card, EmptyState } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './InsightsPage.module.scss';

type Insight = { title: string; detail: string; tone: Tone; page: PageId; value: number };

export function InsightsPage() {
  const dashboard = useDashboard();
  const insights = createMemo<Insight[]>(() => {
    const persona = object(dashboard.data.persona_updates);
    const style = object(dashboard.data.style_learning_reviews);
    const jargon = object(dashboard.data.jargon_stats);
    const backlog = Number(persona.total || 0) + Number(style.total || 0)
      + Math.max(0, Number(jargon.total_candidates || 0) - Number(jargon.confirmed_jargon || 0));
    const filtered = metric(dashboard.data, ['metrics.filtered_messages', 'metrics.messages.filtered']);
    const failures = Object.values(object(object(dashboard.data.health).checks))
      .filter((item) => object(item).status && object(item).status !== 'healthy').length;
    const rows: Insight[] = [];
    if (backlog > 0) rows.push({ title: '审查队列存在积压', detail: `当前约 ${formatCount(backlog)} 条记录等待处理。`, tone: backlog > 20 ? 'danger' : 'warning', page: 'reviews', value: backlog });
    if (filtered > 0) rows.push({ title: '过滤链路持续工作', detail: `${formatCount(filtered)} 条消息因质量或规则未进入学习。`, tone: 'default', page: 'monitoring', value: filtered });
    if (failures > 0) rows.push({ title: '健康检查发现异常', detail: `${formatCount(failures)} 项检查未处于健康状态。`, tone: 'danger', page: 'monitoring', value: failures });
    if (!rows.length) rows.push({ title: '暂未发现需要立即处理的问题', detail: '当前快照没有明显积压或健康告警。', tone: 'success', page: 'overview', value: 0 });
    return rows;
  });
  const copy = async () => {
    const text = insights().map((item) => `- ${item.title}: ${item.detail}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      dashboard.toast('巡检摘要已复制', 'success');
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text; document.body.append(textarea); textarea.select();
      document.execCommand('copy'); textarea.remove();
      dashboard.toast('巡检摘要已复制', 'success');
    }
  };
  return (
    <div class="page">
      <PageHeader title="AI 巡检" description="根据当前 Dashboard 快照生成可执行的关注事项。" icon="auto_awesome" actions={<Button icon="content_copy" onClick={copy}>复制摘要</Button>} />
      <div class={styles['insight-hero']}><span class="material-icons">auto_awesome</span><div><strong>巡检建议只用于导航和辅助判断</strong><p>所有实际审批、删除和配置修改仍需要明确确认。</p></div></div>
      <div class={styles['insight-list']}>
        <For each={insights()} fallback={<EmptyState />}>{(item) =>
          <Card interactive class={`${styles['insight-card']} tone-${item.tone}`} >
            <button onClick={() => dashboard.navigate(item.page)}>
              <div><Badge tone={item.tone}>{item.tone === 'danger' ? '高' : item.tone === 'warning' ? '中' : '提示'}</Badge><strong>{item.title}</strong></div>
              <p>{item.detail}</p><span class="material-icons">arrow_forward</span>
            </button>
          </Card>
        }</For>
      </div>
    </div>
  );
}
