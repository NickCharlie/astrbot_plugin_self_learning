import { createEffect, createSignal, For, on, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { ReviewItem, UnknownRecord } from '../../types/dashboard';
import { list, object, parseJsonOrLines } from '../shared';
import type { ReviewKind } from '../../components/business/ReviewCard';
import { ReviewCard } from '../../components/business/ReviewCard';
import { formatCount, formatDecimal, formatTime, textOrDash } from '../../lib/format';
import { Badge, Button, Card, EmptyState, Input, Pagination, Panel, Textarea } from '../../components/ui';
import { DetailDialog } from '../../components/feedback/DetailDialog';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './ReviewsPage.module.scss';

type BatchAction = 'approve' | 'reject' | 'delete';

const config: Record<ReviewKind, { title: string; endpoint: string; placeholder: string }> = {
  persona: { title: '待审人格', endpoint: '/api/persona_updates', placeholder: '搜索人格更新' },
  style: { title: '风格审查', endpoint: '/api/style_learning/reviews', placeholder: '搜索表达方式' },
  jargon: { title: '黑话审查', endpoint: '/api/jargon', placeholder: '搜索黑话候选' },
};
const KINDS = Object.keys(config) as ReviewKind[];
// 与内嵌插件页 page/reviews 同口径：每个队列首屏 50 条
const QUEUE_LIMIT = 50;

export type ReviewQueues = { persona: ReviewItem[]; styleReviews: ReviewItem[]; jargon: ReviewItem[] };
export type ReviewKeywords = Record<ReviewKind, string>;
const emptyKeywords = (): ReviewKeywords => ({ persona: '', style: '', jargon: '' });
const emptySelection = (): Record<ReviewKind, Set<string>> => ({ persona: new Set(), style: new Set(), jargon: new Set() });

/**
 * 审查队列三栏数据源（与内嵌插件页 reviewQueueItems 同口径）：人格栏排除风格审查；
 * 风格栏优先取人格待审中 review_source === 'style_learning' 的记录，缺失时回退到风格审查列表；
 * 任一栏带搜索词时风格栏直接取风格审查列表（服务端按风格搜索词过滤）。
 */
export function reviewQueueItems(kind: ReviewKind, queues: ReviewQueues, keywords: ReviewKeywords): ReviewItem[] {
  if (kind === 'persona') return queues.persona.filter((item) => item.review_source !== 'style_learning');
  if (kind === 'style') {
    const fromPersona = queues.persona.filter((item) => item.review_source === 'style_learning');
    if (keywords.persona || keywords.style) return queues.styleReviews;
    return fromPersona.length ? fromPersona : queues.styleReviews;
  }
  return queues.jargon;
}

/** 批量按钮：未勾选时作用于当前列出的全部记录，勾选后只作用于选中项。 */
export const reviewBatchLabel = (action: BatchAction, scoped: boolean): string =>
  action === 'approve' ? (scoped ? '通过所选' : '全部通过')
    : action === 'reject' ? (scoped ? '驳回所选' : '全部驳回')
      : (scoped ? '删除所选' : '全部删除');

const actionText = (action: BatchAction) => action === 'approve' ? '通过' : action === 'reject' ? '驳回' : '删除';

export function ReviewsPage() {
  const dashboard = useDashboard();
  const [queues, setQueues] = createSignal<ReviewQueues>({ persona: [], styleReviews: [], jargon: [] });
  const [inputs, setInputs] = createSignal<ReviewKeywords>(emptyKeywords());
  const [applied, setApplied] = createSignal<ReviewKeywords>(emptyKeywords());
  const [selected, setSelected] = createSignal(emptySelection());
  const [styleEdit, setStyleEdit] = createSignal<ReviewItem | null>(null);
  const [styleDraft, setStyleDraft] = createSignal({ description: '', few_shots_content: '', learned_patterns: '' });
  const [savingStyle, setSavingStyle] = createSignal(false);
  const [batches, setBatches] = createSignal<Record<string, unknown>[]>([]);
  const [batchPage, setBatchPage] = createSignal(1);
  const [batchPages, setBatchPages] = createSignal(1);
  const [batchLoading, setBatchLoading] = createSignal(false);

  const items = (kind: ReviewKind) => reviewQueueItems(kind, queues(), applied());
  const selectedItems = (kind: ReviewKind) => items(kind).filter((item) => selected()[kind].has(String(item.id ?? '')));
  const countText = (kind: ReviewKind) => {
    const chosen = selectedItems(kind).length;
    const total = items(kind).length;
    return chosen ? `${formatCount(chosen)}/${formatCount(total)}` : formatCount(total);
  };

  // 三个队列自带检索（与内嵌插件页同一组服务与参数）
  const loadQueues = async (options: { quiet?: boolean } = {}) => {
    const keywords = applied();
    const query = (params: Record<string, string>, keyword: string) => new URLSearchParams(keyword ? { ...params, keyword } : params);
    const responses = await Promise.allSettled([
      api.get<UnknownRecord>(`/api/persona_updates?${query({ limit: String(QUEUE_LIMIT) }, keywords.persona)}`),
      api.get<UnknownRecord>(`/api/style_learning/reviews?${query({ limit: String(QUEUE_LIMIT) }, keywords.style)}`),
      api.get<UnknownRecord>(`/api/jargon/list?${query({ page: '1', page_size: String(QUEUE_LIMIT), confirmed: 'false', pending: 'true' }, keywords.jargon)}`),
    ]);
    const rows = (response: PromiseSettledResult<UnknownRecord>) => response.status === 'fulfilled' ? list<ReviewItem>(response.value) : [];
    const next: ReviewQueues = {
      persona: rows(responses[0]),
      styleReviews: rows(responses[1]),
      jargon: rows(responses[2]).slice(0, QUEUE_LIMIT),
    };
    setQueues(next);
    // 刷新后剔除已不在列表中的勾选项
    setSelected((current) => {
      const pruned = emptySelection();
      for (const kind of KINDS) {
        const valid = new Set(reviewQueueItems(kind, next, keywords).map((item) => String(item.id ?? '')));
        current[kind].forEach((id) => { if (valid.has(id)) pruned[kind].add(id); });
      }
      return pruned;
    });
    const failure = responses.find((response): response is PromiseRejectedResult => response.status === 'rejected');
    if (failure && !options.quiet) dashboard.toast(failure.reason instanceof Error ? failure.reason.message : '加载失败', 'danger');
  };

  const [relearning, setRelearning] = createSignal(false);
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

  onMount(() => {
    loadQueues();
    loadBatches();
  });
  // 顶栏「刷新」、60 秒静默刷新与审查动作后的全局刷新都会同步重新读取三个队列
  createEffect(on(dashboard.lastUpdated, () => { loadQueues({ quiet: true }); }, { defer: true }));

  const search = (kind: ReviewKind) => {
    const current = inputs();
    setApplied({ persona: current.persona.trim(), style: current.style.trim(), jargon: current.jargon.trim() });
    setSelected((value) => ({ ...value, [kind]: new Set<string>() }));
    loadQueues();
  };

  const toggle = (kind: ReviewKind, id: unknown, checked: boolean) => setSelected((current) => {
    const next = new Set(current[kind]);
    const key = String(id ?? '');
    if (checked) next.add(key);
    else next.delete(key);
    return { ...current, [kind]: next };
  });

  const batch = async (kind: ReviewKind, action: BatchAction) => {
    const chosen = selectedItems(kind);
    const scoped = chosen.length > 0;
    const ids = (scoped ? chosen : items(kind))
      .map((item) => kind === 'style' ? String(item.id ?? '').replace(/^style_/, '') : item.id)
      .filter((id) => id !== undefined && id !== null && String(id) !== '');
    if (!ids.length) return dashboard.toast('当前没有可操作的记录', 'warning');
    if (!await dashboard.confirm({
      title: '批量操作确认',
      message: `确定对${scoped ? '选中的' : '当前'} ${ids.length} 条${config[kind].title}执行${actionText(action)}吗？`,
      tone: action === 'approve' ? 'success' : 'danger',
    })) return;
    dashboard.setBusy(true);
    try {
      const endpoint = action === 'delete' ? `${config[kind].endpoint}/batch_delete` : `${config[kind].endpoint}/batch_review`;
      const key = kind === 'persona' ? 'update_ids' : kind === 'style' ? 'review_ids' : 'jargon_ids';
      await api.post(endpoint, action === 'delete' ? { [key]: ids } : { [key]: ids, action });
      dashboard.toast('批量操作已完成', 'success');
      setSelected((current) => ({ ...current, [kind]: new Set<string>() }));
      await dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '批量操作失败', 'danger'); }
    finally { dashboard.setBusy(false); }
  };

  // 风格审查「编辑」：描述 / Few-shot 示例 / 学习模式 JSON（与内嵌插件页同一编辑表单）
  const openStyleEdit = (item: ReviewItem) => {
    const patterns = item.learned_patterns;
    setStyleDraft({
      description: String(item.description ?? item.reason ?? ''),
      few_shots_content: String(item.few_shots_content ?? item.proposed_content ?? ''),
      learned_patterns: typeof patterns === 'string' ? patterns : JSON.stringify(patterns || [], null, 2),
    });
    setStyleEdit(item);
    dashboard.setEditing(true);
  };
  const closeStyleEdit = () => {
    setStyleEdit(null);
    dashboard.setEditing(false);
  };
  const saveStyleEdit = async () => {
    const item = styleEdit();
    if (!item) return;
    const id = String(item.id ?? '').replace(/^style_/, '');
    const draft = styleDraft();
    setSavingStyle(true);
    try {
      await api.put(`/api/style_learning/reviews/${encodeURIComponent(id)}`, {
        description: draft.description,
        few_shots_content: draft.few_shots_content,
        learned_patterns: parseJsonOrLines(draft.learned_patterns),
      });
      dashboard.toast('表达方式已更新', 'success');
      closeStyleEdit();
      await dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '保存失败', 'danger'); }
    finally { setSavingStyle(false); }
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
  // 全局重新学习：不传群组时后端自动选择消息最多的群组（无批次时也可用）
  const relearnAll = async () => {
    if (!await dashboard.confirm({
      title: '重新学习',
      message: '将自动选择消息最多的群组重新学习，可能需要几分钟，确定继续吗？',
      tone: 'warning',
    })) return;
    setRelearning(true);
    try {
      const result = await api.post<{ success?: boolean; message?: string; error?: string }>('/api/relearn', { group_id: 'default' });
      if (result?.success === false) throw new Error(result.error || result.message || '批次操作失败');
      dashboard.toast(result?.message || '重新学习已提交', 'success');
      await loadBatches();
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '批次操作失败', 'danger'); }
    finally { setRelearning(false); }
  };
  return (
    <div class="page">
      <PageHeader title="审查队列" description="集中处理人格更新、表达风格和群聊黑话。" icon="fact_check" />
      <div class={styles['review-columns']}>
        <For each={KINDS}>{(kind) =>
          <Panel title={config[kind].title} actions={
            <div class="inline-actions">
              <Badge>{countText(kind)}</Badge>
              <Button size="sm" tone="success" onClick={() => batch(kind, 'approve')}>{reviewBatchLabel('approve', selectedItems(kind).length > 0)}</Button>
              <Button size="sm" tone="warning" onClick={() => batch(kind, 'reject')}>{reviewBatchLabel('reject', selectedItems(kind).length > 0)}</Button>
              <Button size="sm" tone="danger" onClick={() => batch(kind, 'delete')}>{reviewBatchLabel('delete', selectedItems(kind).length > 0)}</Button>
            </div>
          }>
            <div class={styles['search-row']}>
              <Input
                type="search"
                placeholder={config[kind].placeholder}
                aria-label={config[kind].placeholder}
                value={inputs()[kind]}
                onInput={(event) => {
                  const value = event.currentTarget.value;
                  setInputs((current) => ({ ...current, [kind]: value }));
                }}
                onKeyDown={(event) => event.key === 'Enter' && search(kind)}
              />
              <Button icon="search" onClick={() => search(kind)}>搜索</Button>
            </div>
            <Show when={items(kind).length} fallback={<EmptyState title="队列为空" />}>
              <div class="review-list"><For each={items(kind)}>{(item) =>
                <ReviewCard
                  item={item}
                  kind={kind}
                  selected={selected()[kind].has(String(item.id ?? ''))}
                  onSelect={(checked) => toggle(kind, item.id, checked)}
                  onEdit={kind === 'style' ? () => openStyleEdit(item) : undefined}
                />
              }</For></div>
            </Show>
          </Panel>
        }</For>
      </div>
      <Panel title="最近学习批次" hint="支持重新学习和删除历史批次" actions={<div class="inline-actions"><Button icon="replay" loading={relearning()} onClick={relearnAll}>重新学习</Button><Button icon="refresh" loading={batchLoading()} onClick={loadBatches}>刷新批次</Button></div>}>
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

      <DetailDialog open={Boolean(styleEdit())} title="编辑表达方式" onClose={closeStyleEdit}>
        <div class={styles['edit-form']}>
          <Input label="描述" value={styleDraft().description} onInput={(event) => {
            const value = event.currentTarget.value;
            setStyleDraft((current) => ({ ...current, description: value }));
          }} />
          <Textarea label="Few-shot 示例" rows={7} value={styleDraft().few_shots_content} onInput={(event) => {
            const value = event.currentTarget.value;
            setStyleDraft((current) => ({ ...current, few_shots_content: value }));
          }} />
          <Textarea label="学习模式 JSON" rows={7} value={styleDraft().learned_patterns} onInput={(event) => {
            const value = event.currentTarget.value;
            setStyleDraft((current) => ({ ...current, learned_patterns: value }));
          }} />
          <div class="inline-actions">
            <Button tone="primary" loading={savingStyle()} onClick={saveStyleEdit}>保存</Button>
          </div>
        </div>
      </DetailDialog>
    </div>
  );
}
