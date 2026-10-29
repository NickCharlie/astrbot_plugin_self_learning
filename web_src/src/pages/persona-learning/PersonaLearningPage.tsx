import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { ReviewItem } from '../../types/dashboard';
import { list, object, reviews } from '../shared';
import { formatTime, summarize, textOrDash } from '../../lib/format';
import { reviewAfterPrompt, reviewBeforePrompt } from '../../lib/review';
import { DetailDialog } from '../../components/feedback/DetailDialog';
import { ReviewCard } from '../../components/business/ReviewCard';
import { Badge, Button, Card, EmptyState, Panel } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './PersonaLearningPage.module.scss';

type PersonaRecord = Record<string, unknown>;

const personaIdOf = (item: PersonaRecord): string =>
  String(item.persona_id ?? item.id ?? item.name ?? '');

const personaNameOf = (item: PersonaRecord): string =>
  textOrDash(item.name ?? item.persona_id ?? item.id ?? '未命名人格');

const personaPromptOf = (item: PersonaRecord): string =>
  String(item.system_prompt ?? item.prompt ?? '');

const backupPersonaOf = (detail: PersonaRecord): PersonaRecord =>
  object(detail.original_persona ?? detail.persona_config);

const backupPromptOf = (detail: PersonaRecord): string => {
  const persona = backupPersonaOf(detail);
  return String(persona.prompt ?? persona.system_prompt ?? detail.persona_content ?? '');
};

const reviewedStatus = (item: ReviewItem): string =>
  item.status === 'approved' ? '已通过' : item.status === 'rejected' ? '已驳回' : textOrDash(item.status);

export function PersonaLearningPage() {
  const dashboard = useDashboard();
  const current = () => object(dashboard.data.persona_current);
  const persona = () => object(current().persona);
  const backups = () => list<Record<string, unknown>>(dashboard.data.persona_backups);
  const pending = () => reviews(dashboard.data, 'persona_updates');
  // dashboard 快照已加载 /persona_updates/reviewed，但此前没有任何页面消费它，
  // 已审记录和撤回入口在 WebUI 中不可见（issue #280 同类缺失）。
  const reviewed = () => list<ReviewItem>(dashboard.data.persona_reviewed).slice(0, 8);

  const [personas, setPersonas] = createSignal<PersonaRecord[]>([]);
  const [personaLoading, setPersonaLoading] = createSignal(false);
  const [busy, setBusy] = createSignal('');
  const [backupDetail, setBackupDetail] = createSignal<PersonaRecord | null>(null);
  const [personaDetail, setPersonaDetail] = createSignal<PersonaRecord | null>(null);
  const [reviewedDetail, setReviewedDetail] = createSignal<ReviewItem | null>(null);

  const loadPersonas = async () => {
    setPersonaLoading(true);
    try {
      const payload = await api.get<{ personas?: PersonaRecord[] }>('/api/persona_management/list');
      setPersonas(Array.isArray(payload.personas) ? payload.personas : []);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '人格列表加载失败', 'danger');
    } finally { setPersonaLoading(false); }
  };
  onMount(loadPersonas);

  const backupAction = async (item: Record<string, unknown>, action: 'view' | 'restore' | 'delete') => {
    const id = String(item.id ?? item.backup_id ?? item.name ?? '');
    const query = item.group_id ? `?${new URLSearchParams({ group_id: String(item.group_id) })}` : '';
    if (action === 'view') {
      setBusy(`view-${id}`);
      try {
        const detail = await api.get<PersonaRecord>(`/api/persona_backups/${encodeURIComponent(id)}${query}`);
        setBackupDetail(object(detail));
      } catch (caught) {
        dashboard.toast(caught instanceof Error ? caught.message : '备份详情加载失败', 'danger');
      } finally { setBusy(''); }
      return;
    }
    if (!await dashboard.confirm({ title: action === 'restore' ? '恢复人格备份' : '删除人格备份', message: action === 'restore' ? '当前人格可能被覆盖，确定继续吗？' : '此操作不可撤销，确定删除吗？', tone: 'danger' })) return;
    setBusy(`${action}-${id}`);
    try {
      if (action === 'restore') await api.post(`/api/persona_backups/${encodeURIComponent(id)}/restore`, item.group_id ? { group_id: item.group_id } : {});
      else await api.delete(`/api/persona_backups/${encodeURIComponent(id)}${query}`);
      dashboard.toast('操作已完成', 'success');
      await dashboard.refresh(true);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '备份操作失败', 'danger');
    } finally { setBusy(''); }
  };

  const viewPersona = async (item: PersonaRecord) => {
    const id = personaIdOf(item);
    if (!id) return setPersonaDetail(item);
    setBusy(`persona-${id}`);
    try {
      setPersonaDetail(object(await api.get<PersonaRecord>(`/api/persona_management/get/${encodeURIComponent(id)}`)));
    } catch (caught) {
      // 详情接口失败时回退到列表数据，列表本身已包含提示词内容
      setPersonaDetail(item);
      dashboard.toast(caught instanceof Error ? caught.message : '人格详情加载失败', 'warning');
    } finally { setBusy(''); }
  };

  const exportPersona = async (item: PersonaRecord) => {
    const id = personaIdOf(item);
    if (!id) return;
    setBusy(`export-${id}`);
    try {
      const data = await api.get<PersonaRecord>(`/api/persona_management/export/${encodeURIComponent(id)}`);
      const text = JSON.stringify(data, null, 2);
      const blob = new Blob([text], { type: 'application/json' });
      const canObjectUrl = typeof URL.createObjectURL === 'function';
      const href = canObjectUrl ? URL.createObjectURL(blob) : `data:application/json;charset=utf-8,${encodeURIComponent(text)}`;
      const link = document.createElement('a');
      link.href = href;
      link.download = `persona_${id}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      if (canObjectUrl) URL.revokeObjectURL(href);
      dashboard.toast('人格配置已导出', 'success');
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '人格导出失败', 'danger');
    } finally { setBusy(''); }
  };

  const revertReview = async (item: ReviewItem) => {
    const id = String(item.id ?? '');
    if (!id) return;
    if (!await dashboard.confirm({ title: '撤回审查决定', message: '撤回后该记录会重新回到待审队列；若记录已被他人处理，撤回会覆盖新的审查状态。确定继续吗？', tone: 'warning', confirmText: '确认撤回' })) return;
    setBusy(`revert-${id}`);
    try {
      await api.post(`/api/persona_updates/${encodeURIComponent(id)}/revert`, { reason: 'WebUI 撤回' });
      dashboard.toast('已撤回审查决定', 'success');
      await dashboard.refresh(true);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '撤回失败', 'danger');
    } finally { setBusy(''); }
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
        <Panel title="人格备份" hint="可查看备份内容，恢复操作会先要求确认">
          <div class={styles['backup-list']}>
            <For each={backups()} fallback={<EmptyState title="暂无备份" />}>{(item) =>
              <Card class={styles['backup-card']}>
                <div><strong>{textOrDash(item.backup_name ?? item.name ?? item.id)}</strong><small>{formatTime(item.created_at ?? item.timestamp)}</small></div>
                <div class="inline-actions">
                  <Button size="sm" loading={busy() === `view-${String(item.id ?? '')}`} onClick={() => backupAction(item, 'view')}>查看备份</Button>
                  <Button size="sm" tone="warning" onClick={() => backupAction(item, 'restore')}>恢复</Button>
                  <Button size="sm" tone="danger" onClick={() => backupAction(item, 'delete')}>删除</Button>
                </div>
              </Card>
            }</For>
          </div>
        </Panel>
      </div>
      <Panel
        title="人格列表"
        hint="浏览 AstrBot 中的人格配置，可查看完整提示词或导出为 JSON"
        actions={<Button icon="refresh" loading={personaLoading()} onClick={loadPersonas}>刷新人格式</Button>}
      >
        <div class={styles['persona-list']}>
          <For each={personas()} fallback={<EmptyState title="暂无人格列表" detail="AstrBot PersonaManager 未提供人格数据。" />}>{(item) =>
            <Card class={styles['persona-card']}>
              <div>
                <strong>{personaNameOf(item)}</strong>
                <small>{textOrDash(personaIdOf(item))} · 提示词 {personaPromptOf(item).length} 字 · 示例对话 {list(item.begin_dialogs).length} 条</small>
              </div>
              <div class="inline-actions">
                <Button size="sm" loading={busy() === `persona-${personaIdOf(item)}`} onClick={() => viewPersona(item)}>查看人格</Button>
                <Button size="sm" loading={busy() === `export-${personaIdOf(item)}`} onClick={() => exportPersona(item)}>导出人格</Button>
              </div>
            </Card>
          }</For>
        </div>
      </Panel>
      <Panel title="最近已审查" hint="撤回后记录会重新进入待审队列">
        <div class={styles['reviewed-list']}>
          <For each={reviewed()} fallback={<EmptyState title="暂无已审查记录" />}>{(item) =>
            <Card class={styles['reviewed-card']}>
              <div class={styles['reviewed-head']}>
                <div>
                  <strong>{textOrDash(item.update_type ?? item.title ?? item.review_source ?? `#${item.id}`)}</strong>
                  <small>{formatTime(item.review_time)} · {textOrDash(item.review_source ?? item.group_id)}</small>
                </div>
                <Badge tone={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'default'}>{reviewedStatus(item)}</Badge>
              </div>
              <p>{textOrDash(String(item.proposed_content ?? item.new_content ?? item.reason ?? '').slice(0, 120))}</p>
              <div class="inline-actions">
                <Button size="sm" onClick={() => setReviewedDetail(item)}>查看详情</Button>
                <Button size="sm" tone="warning" loading={busy() === `revert-${String(item.id ?? '')}`} onClick={() => revertReview(item)}>撤回</Button>
              </div>
            </Card>
          }</For>
        </div>
      </Panel>
      <Panel title="待审人格更新" hint="点击「查看变更详情」展开逐行差异">
        <div class="review-list"><For each={pending()} fallback={<EmptyState title="没有待审人格更新" />}>{(item) => <ReviewCard item={item} kind="persona" />}</For></div>
      </Panel>

      <DetailDialog open={Boolean(backupDetail())} title="备份详情" onClose={() => setBackupDetail(null)}>
        <Show when={backupDetail()} keyed>{(detail) => {
          const summary = object(detail.summary);
          const dialogs = list<unknown>(detail.imitation_dialogues);
          return <>
            <p class={styles['detail-line']}>
              {textOrDash(summary.backup_name ?? detail.backup_name)} · 群组 {textOrDash(summary.group_id ?? detail.group_id)} · {formatTime(summary.timestamp ?? detail.timestamp)}
            </p>
            <p class={styles['detail-line']}>备份原因：{textOrDash(summary.reason ?? detail.reason ?? detail.backup_reason)}</p>
            <h4>人格提示词</h4>
            <pre>{backupPromptOf(detail) || '（备份中没有提示词内容）'}</pre>
            <Show when={dialogs.length}>
              <h4>示例对话（{dialogs.length} 条）</h4>
              <pre>{summarize(dialogs)}</pre>
            </Show>
            <details><summary>查看原始备份数据</summary><pre>{summarize(detail)}</pre></details>
          </>;
        }}</Show>
      </DetailDialog>

      <DetailDialog open={Boolean(personaDetail())} title="人格详情" onClose={() => setPersonaDetail(null)}>
        <Show when={personaDetail()} keyed>{(detail) =>
          <>
            <p class={styles['detail-line']}>
              {personaNameOf(detail)} · ID {textOrDash(personaIdOf(detail))} · 示例对话 {list(detail.begin_dialogs).length} 条 · 工具 {list(detail.tools).length} 个
            </p>
            <h4>系统提示词</h4>
            <pre>{personaPromptOf(detail) || '（空）'}</pre>
            <Show when={list(detail.begin_dialogs).length}>
              <h4>示例对话</h4>
              <pre>{summarize(detail.begin_dialogs)}</pre>
            </Show>
            <details><summary>查看原始人格数据</summary><pre>{summarize(detail)}</pre></details>
          </>
        }</Show>
      </DetailDialog>

      <DetailDialog open={Boolean(reviewedDetail())} title="已审查记录" onClose={() => setReviewedDetail(null)}>
        <Show when={reviewedDetail()} keyed>{(item) =>
          <>
            <p class={styles['detail-line']}>{reviewedStatus(item)} · {formatTime(item.review_time)} · 备注：{textOrDash(item.reviewer_comment)}</p>
            <Show when={reviewBeforePrompt(item) || reviewAfterPrompt(item)}>
              <h4>变更前</h4>
              <pre>{reviewBeforePrompt(item) || '（空）'}</pre>
              <h4>变更后</h4>
              <pre>{reviewAfterPrompt(item) || '（空）'}</pre>
            </Show>
            <details><summary>查看原始审查数据</summary><pre>{summarize(item)}</pre></details>
          </>
        }</Show>
      </DetailDialog>
    </div>
  );
}
