import { For, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object, reviews } from '../shared';
import { formatTime, summarize, textOrDash } from '../../lib/format';
import { ReviewCard } from '../../components/business/ReviewCard';
import { Badge, Button, Card, EmptyState, Panel } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './PersonaLearningPage.module.scss';

export function PersonaLearningPage() {
  const dashboard = useDashboard();
  const current = () => object(dashboard.data.persona_current);
  const persona = () => object(current().persona);
  const backups = () => list<Record<string, unknown>>(dashboard.data.persona_backups);
  const pending = () => reviews(dashboard.data, 'persona_updates');
  const backupAction = async (item: Record<string, unknown>, action: 'view' | 'restore' | 'delete') => {
    const id = String(item.id ?? item.backup_id ?? item.name ?? '');
    const query = item.group_id ? `?${new URLSearchParams({ group_id: String(item.group_id) })}` : '';
    if (action !== 'view' && !await dashboard.confirm({ title: action === 'restore' ? '恢复人格备份' : '删除人格备份', message: action === 'restore' ? '当前人格可能被覆盖，确定继续吗？' : '此操作不可撤销，确定删除吗？', tone: 'danger' })) return;
    try {
      if (action === 'view') {
        const detail = await api.get(`/api/persona_backups/${encodeURIComponent(id)}${query}`);
        dashboard.toast(`已读取备份：${String(object(detail).backup_name ?? id)}`, 'success');
      } else if (action === 'restore') await api.post(`/api/persona_backups/${encodeURIComponent(id)}/restore`, item.group_id ? { group_id: item.group_id } : {});
      else await api.delete(`/api/persona_backups/${encodeURIComponent(id)}${query}`);
      if (action !== 'view') { dashboard.toast('操作已完成', 'success'); await dashboard.refresh(true); }
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '备份操作失败', 'danger'); }
  };
  return (
    <div class="page">
      <PageHeader title="人格学习" description="观察当前人格状态、待审更新和可恢复备份。" icon="person_search" />
      <div class="two-column">
        <Panel title="当前人格" hint="默认群组的实时人格快照">
          <Show when={Object.keys(current()).length} fallback={<EmptyState title="暂无人格快照" />}>
            <div class={styles['persona-current']}>
              <span class="material-icons">face</span>
              <div><h3>{textOrDash(persona().name ?? persona().persona_id ?? 'Default Persona')}</h3><Badge tone={current().degraded ? 'warning' : 'success'}>{current().degraded ? '降级预览' : '当前生效'}</Badge></div>
              <p>{textOrDash(current().prompt_preview ?? persona().prompt ?? persona().system_prompt)}</p>
              <details><summary>查看完整状态</summary><pre>{summarize(current())}</pre></details>
            </div>
          </Show>
        </Panel>
        <Panel title="人格备份" hint="恢复操作会先要求确认">
          <div class={styles['backup-list']}>
            <For each={backups()} fallback={<EmptyState title="暂无备份" />}>{(item) =>
              <Card class={styles['backup-card']}>
                <div><strong>{textOrDash(item.backup_name ?? item.name ?? item.id)}</strong><small>{formatTime(item.created_at)}</small></div>
                <div class="inline-actions"><Button size="sm" onClick={() => backupAction(item, 'view')}>查看</Button><Button size="sm" tone="warning" onClick={() => backupAction(item, 'restore')}>恢复</Button><Button size="sm" tone="danger" onClick={() => backupAction(item, 'delete')}>删除</Button></div>
              </Card>
            }</For>
          </div>
        </Panel>
      </div>
      <Panel title="待审人格更新" hint="变更预览保留逐行差异">
        <div class="review-list"><For each={pending()} fallback={<EmptyState title="没有待审人格更新" />}>{(item) => <ReviewCard item={item} kind="persona" />}</For></div>
      </Panel>
    </div>
  );
}
