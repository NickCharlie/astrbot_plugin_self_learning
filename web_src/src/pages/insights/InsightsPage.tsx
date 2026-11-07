import { createMemo, For } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { Badge, Button, Card, EmptyState } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import { buildInsights, insightLevel } from './insights';
import styles from './InsightsPage.module.scss';

export function InsightsPage() {
  const dashboard = useDashboard();
  const insights = createMemo(() => buildInsights(dashboard.data, dashboard.integrations()));
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
              <div><Badge tone={item.tone}>{insightLevel(item.tone)}</Badge><strong>{item.title}</strong></div>
              <p>{item.detail}</p><span class="material-icons">arrow_forward</span>
            </button>
          </Card>
        }</For>
      </div>
    </div>
  );
}
