import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object, reviews } from '../shared';
import type { ReviewKind, } from '../../components/business/ReviewCard';
import { ReviewCard } from '../../components/business/ReviewCard';
import { formatDecimal, formatTime, textOrDash } from '../../lib/format';
import { Button, Card, EmptyState, Pagination, Panel } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './ReviewsPage.module.scss';

const config: Record<ReviewKind, { title: string; endpoint: string }> = {
  persona: { title: '待审人格', endpoint: '/api/persona_updates' },
  style: { title: '风格审查', endpoint: '/api/style_learning/reviews' },
  jargon: { title: '黑话审查', endpoint: '/api/jargon' },
};

export function ReviewsPage() {
  const dashboard = useDashboard();
  const [batches, setBatches] = createSignal<Record<string, unknown>[]>([]);
  const [batchPage, setBatchPage] = createSignal(1);
  const [batchPages, setBatchPages] = createSignal(1);
  const [batchLoading, setBatchLoading] = createSignal(false);
  const loadBatches = async () => {
    setBatchLoading(true);
    try {
      const payload = await api.get<Record<string, unknown>>(`/api/batches?${new URLSearchParams({ page: String(batchPage()), page_size: '10' })}`);
      const nested = object(payload.data);
      const rows = list<Record<string, unknown>>(nested.batches ?? payload.batches ?? nested);
      setBatches(rows);
      setBatchPages(Math.max(1, Number(nested.total_pages ?? payload.total_pages ?? 1)));
    } catch {
      const trends = await api.get<Record<string, unknown>>('/api/metrics/trends').catch((): Record<string, unknown> => ({}));
      setBatches(list<Record<string, unknown>>(object(trends).recent_batches));
      setBatchPages(1);
    } finally { setBatchLoading(false); }
  };
  onMount(loadBatches);
  const items = (kind: ReviewKind) => kind === 'persona'
    ? reviews(dashboard.data, 'persona_updates').filter((item) => item.review_source !== 'style_learning')
    : kind === 'style'
      ? (() => {
        const fromPersona = reviews(dashboard.data, 'persona_updates').filter((item) => item.review_source === 'style_learning');
        return fromPersona.length ? fromPersona : reviews(dashboard.data, 'style_learning_reviews');
      })()
      : reviews(dashboard.data, 'jargon_reviews');
  const batch = async (kind: ReviewKind, action: 'approve' | 'reject' | 'delete') => {
    const ids = items(kind)
      .map((item) => kind === 'style' ? String(item.id ?? '').replace(/^style_/, '') : item.id)
      .filter((id) => id !== undefined && id !== null && String(id) !== '');
    if (!ids.length) return dashboard.toast('当前没有可操作的记录', 'warning');
    if (!await dashboard.confirm({ title: '批量操作确认', message: `确定对当前 ${ids.length} 条${config[kind].title}执行${action === 'approve' ? '通过' : action === 'reject' ? '驳回' : '删除'}吗？`, tone: action === 'approve' ? 'success' : 'danger' })) return;
    dashboard.setBusy(true);
    try {
      const endpoint = action === 'delete' ? `${config[kind].endpoint}/batch_delete` : `${config[kind].endpoint}/batch_review`;
      const key = kind === 'persona' ? 'update_ids' : kind === 'style' ? 'review_ids' : 'jargon_ids';
      await api.post(endpoint, action === 'delete' ? { [key]: ids } : { [key]: ids, action });
      dashboard.toast('批量操作已完成', 'success');
      await dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '批量操作失败', 'danger'); }
    finally { dashboard.setBusy(false); }
  };
  const batchRecordAction = async (item: Record<string, unknown>, action: 'relearn' | 'delete') => {
    const id = String(action === 'relearn' ? item.group_id ?? '' : item.id ?? item.batch_id ?? '');
    if (!id) return;
    if (!await dashboard.confirm({
      title: action === 'relearn' ? '重新学习' : '删除学习批次',
      message: action === 'relearn' ? '重新学习可能需要几分钟，确定继续吗？' : '删除后不可撤销，确定继续吗？',
      tone: action === 'delete' ? 'danger' : 'warning',
    })) return;
    try {
      if (action === 'relearn') await api.post('/api/relearn', { group_id: id });
      else await api.delete(`/api/batches/${encodeURIComponent(id)}`);
      dashboard.toast('批次操作已完成', 'success');
      await loadBatches();
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '批次操作失败', 'danger'); }
  };
  return (
    <div class="page">
      <PageHeader title="审查队列" description="集中处理人格更新、表达风格和群聊黑话。" icon="fact_check" />
      <div class={styles['review-columns']}>
        <For each={Object.keys(config) as ReviewKind[]}>{(kind) =>
          <Panel title={config[kind].title} actions={
            <div class="inline-actions">
              <Button size="sm" tone="success" onClick={() => batch(kind, 'approve')}>全部通过</Button>
              <Button size="sm" tone="warning" onClick={() => batch(kind, 'reject')}>全部驳回</Button>
              <Button size="sm" tone="danger" onClick={() => batch(kind, 'delete')}>全部删除</Button>
            </div>
          }>
            <Show when={items(kind).length} fallback={<EmptyState title="队列为空" />}>
              <div class="review-list"><For each={items(kind)}>{(item) => <ReviewCard item={item} kind={kind} />}</For></div>
            </Show>
          </Panel>
        }</For>
      </div>
      <Panel title="最近学习批次" hint="支持重新学习和删除历史批次" actions={<Button icon="refresh" loading={batchLoading()} onClick={loadBatches}>刷新批次</Button>}>
        <div class={styles['batch-grid']}>
          <For each={batches()} fallback={<EmptyState title="暂无批次记录" />}>{(item) =>
            <Card class={styles['batch-card']}>
              <div class={styles['batch-card-head']}><strong>{textOrDash(item.batch_name ?? item.batch_id ?? '学习批次')}</strong><span>{item.quality_score === undefined ? '--' : `quality ${formatDecimal(item.quality_score, Number(item.quality_score) < 1 ? 3 : 1)}`}</span></div>
              <p>群组 {textOrDash(item.group_id)} · 开始 {formatTime(item.start_time)} · 结束 {formatTime(item.end_time)}</p>
              <div class="inline-actions">
                <Show when={item.group_id}><Button size="sm" onClick={() => batchRecordAction(item, 'relearn')}>重跑学习</Button></Show>
                <Show when={item.id ?? item.batch_id}><Button size="sm" tone="danger" onClick={() => batchRecordAction(item, 'delete')}>删除批次</Button></Show>
              </div>
            </Card>
          }</For>
        </div>
        <Pagination page={batchPage()} totalPages={batchPages()} disabled={batchLoading()} onChange={(next) => { setBatchPage(next); queueMicrotask(loadBatches); }} />
      </Panel>
    </div>
  );
}
