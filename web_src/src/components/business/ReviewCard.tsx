import { createSignal, For, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { ReviewItem } from '../../types/dashboard';
import { buildLineDiff } from '../../lib/diff';
import {
  formatDialogLines, reviewAfterPrompt, reviewBeforePrompt, reviewBeginDialogs,
  reviewChangeMeta, reviewChangePreview, reviewHasChange,
} from '../../lib/review';
import { formatTime, summarize, textOrDash } from '../../lib/format';
import { Badge, Button, Card } from '../ui';
import styles from './ReviewCard.module.scss';

export type ReviewKind = 'persona' | 'style' | 'jargon';

const titleFor = (item: ReviewItem) =>
  textOrDash(item.title ?? item.content ?? item.jargon ?? item.pattern ?? item.update_type ?? item.description ?? `#${item.id}`);

export function ReviewCard(props: { item: ReviewItem; kind: ReviewKind; onDone?: () => void }) {
  const dashboard = useDashboard();
  const [busy, setBusy] = createSignal(false);
  const id = () => String(props.item.id ?? '');
  const execute = async (action: 'approve' | 'reject' | 'delete') => {
    if (!id()) return;
    const destructive = action !== 'approve';
    if (!await dashboard.confirm({
      title: action === 'delete' ? '删除审查记录' : '审查确认',
      message: `确定${action === 'approve' ? '通过' : action === 'reject' ? '驳回' : '删除'}“${titleFor(props.item)}”吗？`,
      confirmText: action === 'approve' ? '批准' : action === 'reject' ? '驳回' : '删除',
      tone: destructive ? 'danger' : 'success',
    })) return;
    setBusy(true);
    try {
      if (props.kind === 'persona') {
        if (action === 'delete') await api.post(`/api/persona_updates/${encodeURIComponent(id())}/delete`, {});
        else await api.post(`/api/persona_updates/${encodeURIComponent(id())}/review`, { action });
      } else if (props.kind === 'style') {
        const reviewId = id().replace(/^style_/, '');
        if (action === 'delete') await api.delete(`/api/style_learning/reviews/${encodeURIComponent(reviewId)}`);
        else await api.post(`/api/style_learning/reviews/${encodeURIComponent(reviewId)}/${action}`, {});
      } else if (props.kind === 'jargon') {
        if (action === 'delete') await api.delete(`/api/jargon/${encodeURIComponent(id())}`);
        else await api.post(`/api/jargon/${encodeURIComponent(id())}/review`, { action });
      }
      dashboard.toast('操作已完成', 'success');
      await dashboard.refresh(true);
      props.onDone?.();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '操作失败', 'danger');
    } finally { setBusy(false); }
  };
  // 后端把快照放在 change_preview/change_snapshot 中；只读顶层字段会让
  // 「查看变更详情」整块消失，导致审查人看不到修改内容（issue #280）。
  const before = () => reviewBeforePrompt(props.item);
  const after = () => reviewAfterPrompt(props.item);
  const dialogDiff = () => reviewBeginDialogs(props.item);
  const meta = () => reviewChangeMeta(props.item);
  const proposedContent = () => {
    const value = reviewChangePreview(props.item).proposed_content ?? props.item.proposed_content;
    return typeof value === 'string' ? value : '';
  };
  return (
    <Card class={styles['review-card']}>
      <div class={styles['review-card-head']}>
        <div><strong>{titleFor(props.item)}</strong><small>{formatTime(props.item.created_at)}</small></div>
        <Badge tone={props.item.status === 'approved' ? 'success' : props.item.status === 'rejected' ? 'danger' : 'warning'}>
          {textOrDash(props.item.status ?? 'pending')}
        </Badge>
      </div>
      <Show when={props.item.definition || props.item.meaning || props.item.review_detail}>
        <p>{textOrDash(props.item.definition ?? props.item.meaning ?? props.item.review_detail)}</p>
      </Show>
      <Show when={reviewHasChange(props.item) || meta().length || proposedContent()}>
        <details class={styles['review-diff']}>
          <summary>查看变更详情</summary>
          <Show when={props.kind !== 'jargon' && (before() || after())}>
            <div class={styles['diff-lines']}>
              <For each={buildLineDiff(before(), after())}>{(line) =>
                <div class={`${styles['diff-line']} ${styles[line.kind] || ''}`}><span>{line.kind === 'add' ? '+' : line.kind === 'remove' ? '−' : ' '}</span>{line.text || ' '}</div>
              }</For>
            </div>
          </Show>
          <Show when={props.kind !== 'jargon' && (dialogDiff().before.length > 0 || dialogDiff().after.length > 0)}>
            <h4 class={styles['review-section-title']}>示例对话变化</h4>
            <div class={styles['diff-lines']}>
              <For each={buildLineDiff(formatDialogLines(dialogDiff().before), formatDialogLines(dialogDiff().after))}>{(line) =>
                <div class={`${styles['diff-line']} ${styles[line.kind] || ''}`}><span>{line.kind === 'add' ? '+' : line.kind === 'remove' ? '−' : ' '}</span>{line.text || ' '}</div>
              }</For>
            </div>
          </Show>
          <Show when={meta().length}><p class={styles['review-meta']}>{meta().join(' · ')}</p></Show>
          <Show when={proposedContent()}>
            <details class={styles['review-proposal']}>
              <summary>建议内容原文（{proposedContent().length} 字）</summary>
              <pre>{proposedContent()}</pre>
            </details>
          </Show>
        </details>
      </Show>
      <Show when={props.item.pattern_details || props.item.few_shot_pairs}>
        <details><summary>结构化信息</summary><pre>{summarize(props.item.pattern_details ?? props.item.few_shot_pairs)}</pre></details>
      </Show>
      <details class={styles['review-raw']}>
        <summary>查看原始审查数据</summary>
        <pre>{summarize(props.item)}</pre>
      </details>
      <div class={styles['review-actions']}>
        <Button size="sm" tone="success" icon="check" loading={busy()} onClick={() => execute('approve')}>通过</Button>
        <Button size="sm" tone="warning" icon="close" loading={busy()} onClick={() => execute('reject')}>驳回</Button>
        <Button size="sm" tone="danger" icon="delete" loading={busy()} onClick={() => execute('delete')}>删除</Button>
      </div>
    </Card>
  );
}
