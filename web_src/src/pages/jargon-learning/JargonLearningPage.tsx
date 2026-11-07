import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { JargonItem, Paginated, Tone } from '../../types/dashboard';
import { list, object } from '../shared';
import { formatCount, formatTime, textOrDash } from '../../lib/format';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge, Button, EmptyState, Input, Pagination, Panel, Select, StatCard, Textarea } from '../../components/ui';
import styles from './JargonLearningPage.module.scss';

type JargonFilter = 'all' | 'pending' | 'confirmed' | 'unconfirmed';
type JargonScope = 'all' | 'global' | 'local';
type JargonBatchAction = 'approve' | 'reject' | 'delete';

export function buildJargonListParams(input: {
  page: number;
  pageSize: number;
  filter: JargonFilter;
  search: string;
  scope?: JargonScope;
}) {
  const params = new URLSearchParams({
    page: String(input.page),
    page_size: String(input.pageSize),
  });
  const keyword = input.search.trim();
  if (keyword) params.set('keyword', keyword);
  if (input.filter === 'pending') params.set('pending', 'true');
  else if (input.filter === 'confirmed') params.set('confirmed', 'true');
  else if (input.filter === 'unconfirmed') params.set('confirmed', 'false');
  // 范围筛选（与内嵌插件页同一后端参数 filter=global|local）
  if (input.scope === 'global' || input.scope === 'local') params.set('filter', input.scope);
  return params;
}

// is_complete 只表示审查/推断已结束；is_jargon 明确为 false 才是人工驳回
// （推理判定为非黑话时也会写 false）。导入等只标记完成的情况用中性文案，
// 避免把“推断完成但未定论”误标为已驳回（issue #274）。
const jargonBadge = (item: JargonItem): { tone: Tone; label: string } => {
  if (item.is_confirmed) return { tone: 'success', label: '已确认' };
  if (!item.is_complete) return { tone: 'warning', label: textOrDash(item.status ?? '待审') };
  return item.is_jargon === false
    ? { tone: 'danger', label: '已驳回' }
    : { tone: 'default', label: '已完成' };
};

export function JargonLearningPage() {
  const dashboard = useDashboard();
  const [items, setItems] = createSignal<JargonItem[]>([]);
  const [page, setPage] = createSignal(1);
  const [totalPages, setTotalPages] = createSignal(1);
  const [filter, setFilter] = createSignal<JargonFilter>('all');
  const [scope, setScope] = createSignal<JargonScope>('all');
  const [search, setSearch] = createSignal('');
  const [loading, setLoading] = createSignal(false);
  const [selected, setSelected] = createSignal<Set<string>>(new Set());
  const [editing, setEditing] = createSignal<string | null>(null);
  const [draft, setDraft] = createSignal({ content: '', meaning: '' });
  const [showImport, setShowImport] = createSignal(false);
  const [groups, setGroups] = createSignal<Array<{ group_id: string; group_name: string; count?: number }>>([]);
  const [importScope, setImportScope] = createSignal('__global__');
  const [importText, setImportText] = createSignal('');
  const [importing, setImporting] = createSignal(false);
  const [importResult, setImportResult] = createSignal<{ message: string; details?: { failed: Array<{ line: number; term: string; reason: string }> } } | null>(null);
  // 读数与首页 / 内嵌插件页同源：全局黑话统计
  const stats = () => {
    const raw = object(dashboard.data.jargon_stats);
    return Object.keys(object(raw.data)).length ? object(raw.data) : raw;
  };
  const load = async () => {
    setLoading(true);
    try {
      const params = buildJargonListParams({ page: page(), pageSize: 10, filter: filter(), search: search(), scope: scope() });
      const payload = await api.get<Paginated<JargonItem>>(`/api/jargon/list?${params}`);
      const rows = list<JargonItem>(payload);
      setItems(rows);
      // 关键词检索返回全部匹配（单页）；普通列表按后端分页（每页 10 条）
      setTotalPages(Math.max(1, Number(payload.total_pages ?? (search().trim() ? 1 : Math.ceil(Number(payload.total ?? rows.length) / 10)))));
      const visible = new Set(rows.map((item) => String(item.id)));
      setSelected((current) => new Set([...current].filter((id) => visible.has(id))));
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '黑话加载失败', 'danger'); }
    finally { setLoading(false); }
  };
  // 查询 / 状态 / 范围变化都回到第 1 页重新检索（与内嵌插件页一致）
  const query = () => { setPage(1); load(); };
  onMount(load);
  onMount(() => { loadGroups(); });
  const loadGroups = async () => {
    try {
      const payload = await api.get<{ groups?: Array<Record<string, unknown>> }>('/api/jargon/groups');
      setGroups((payload.groups ?? []).map((group) => ({
        group_id: String(group.group_id ?? group.id ?? ''),
        group_name: String(group.group_name ?? group.group_id ?? '未知群组'),
        count: Number(group.count ?? group.confirmed_jargon ?? 0),
      })).filter((group) => group.group_id));
    } catch { /* 群组列表加载失败不阻塞页面 */ }
  };
  const toggleSelect = (id: string, checked: boolean) => setSelected((current) => {
    const next = new Set(current);
    if (checked) next.add(id);
    else next.delete(id);
    return next;
  });
  const edit = (item: JargonItem) => {
    setEditing(String(item.id));
    dashboard.setEditing(true);
    setDraft({ content: String(item.content ?? item.jargon ?? ''), meaning: String(item.meaning ?? item.definition ?? '') });
  };
  const cancel = () => { setEditing(null); dashboard.setEditing(false); };
  const save = async (id: string) => {
    if (!draft().content.trim()) return dashboard.toast('词条不能为空', 'warning');
    try {
      await api.put(`/api/jargon/${encodeURIComponent(id)}`, draft());
      dashboard.toast('词条已保存', 'success'); cancel(); await load();
      dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '保存失败', 'danger'); }
  };
  const action = async (item: JargonItem, name: 'approve' | 'reject' | 'delete' | 'toggle_global') => {
    const id = String(item.id);
    if (name === 'delete' && !await dashboard.confirm({ title: '删除黑话', message: `确定删除“${item.content ?? item.jargon}”吗？`, tone: 'danger' })) return;
    try {
      if (name === 'delete') await api.delete(`/api/jargon/${encodeURIComponent(id)}`);
      else if (name === 'toggle_global') await api.post(`/api/jargon/${encodeURIComponent(id)}/toggle_global`, {});
      else await api.post(`/api/jargon/${encodeURIComponent(id)}/review`, { action: name });
      dashboard.toast('操作已完成', 'success'); await load();
      // 审查动作改变待审队列，同步刷新首页/AI 巡检共享的全局快照
      dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '操作失败', 'danger'); }
  };
  // 批量确认 / 驳回 / 删除（与内嵌插件页同一确认文案）
  const batchAction = async (name: JargonBatchAction) => {
    const ids = [...selected()];
    if (!ids.length) return dashboard.toast('请先选择黑话条目', 'warning');
    const label = name === 'approve' ? '确认' : name === 'reject' ? '驳回' : '删除';
    if (!await dashboard.confirm({
      title: '批量操作确认',
      message: `确定批量${label}选中的 ${ids.length} 条黑话？`,
      confirmText: label,
      tone: name === 'approve' ? 'success' : 'danger',
    })) return;
    try {
      const payload = name === 'delete'
        ? await api.post<{ message?: string }>('/api/jargon/batch_delete', { jargon_ids: ids })
        : await api.post<{ message?: string }>('/api/jargon/batch_review', { jargon_ids: ids, action: name });
      dashboard.toast(payload?.message || '批量黑话操作完成', 'success');
      setSelected(new Set<string>());
      await load();
      dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '批量操作失败', 'danger'); }
  };
  const runImport = async () => {
    if (!importText().trim()) return dashboard.toast('请先填写要导入的词条', 'warning');
    const target = importScope();
    setImporting(true);
    setImportResult(null);
    try {
      const payload = await api.post<{ message: string; details?: { failed: Array<{ line: number; term: string; reason: string }> } }>('/api/jargon/import', {
        text: importText(),
        group_id: target === '__global__' ? '' : target,
        is_global: target === '__global__',
      });
      setImportResult(payload);
      dashboard.toast(payload.message || '导入完成', 'success');
      setPage(1);
      await load();
      dashboard.refresh(true);
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '导入失败', 'danger'); }
    finally { setImporting(false); }
  };
  return (
    <div class="page">
      <PageHeader title="黑话学习" description="检索、编辑和审查从群聊语境中学习到的词条。" icon="forum" />
      <div class="metrics-grid">
        <StatCard label="候选词" value={formatCount(stats().total_candidates)} />
        <StatCard label="已确认" value={formatCount(stats().confirmed_jargon)} />
        <StatCard label="推断完成" value={formatCount(stats().completed_inference)} />
        <StatCard label="活跃群组" value={formatCount(stats().active_groups)} />
      </div>
      <Show when={showImport()}>
        <Panel title="导入黑话" hint="每行一条，支持「关键词 = 解释」「关键词：解释」「关键词|解释」等分隔；# 或 // 开头为注释行" icon="upload">
          <div class={styles['import-grid']}>
            <Select label="导入范围" value={importScope()} onChange={(event) => setImportScope(event.currentTarget.value)}>
              <option value="__global__">全局共享（所有群生效）</option>
              <For each={groups()}>{(group) =>
                <option value={group.group_id}>{group.group_name}（{group.count ?? 0} 条）</option>
              }</For>
            </Select>
            <Textarea label="词条列表" rows={8} value={importText()} onInput={(event) => setImportText(event.currentTarget.value)}
              placeholder={'摸鱼 = 上班时间偷懒\nyyds：永远的神\n绝绝子\n# 注释行会被忽略'} />
            <div class="inline-actions">
              <Button tone="primary" icon="upload" loading={importing()} disabled={importing() || !importText().trim()} onClick={runImport}>导入</Button>
              <Button onClick={() => setShowImport(false)}>收起</Button>
            </div>
            <Show when={importResult()}>
              <div class={styles['import-report']}>
                <strong>{importResult()!.message}</strong>
                <Show when={importResult()!.details?.failed?.length}>
                  <ul><For each={importResult()!.details!.failed}>{(failure) =>
                    <li>第 {failure.line} 行「{failure.term}」：{failure.reason}</li>
                  }</For></ul>
                </Show>
              </div>
            </Show>
          </div>
        </Panel>
      </Show>
      <Panel title="黑话词库" hint="支持分页、状态筛选和原地编辑" actions={
        <div class="inline-actions">
          <Button icon="upload" onClick={() => setShowImport(!showImport())}>导入黑话</Button>
          <Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>
        </div>
      }>
        <div class={styles['filter-bar']}>
          <Input label="搜索" placeholder="词条或释义" value={search()} onInput={(event) => setSearch(event.currentTarget.value)} onKeyDown={(event) => event.key === 'Enter' && query()} />
          <Select label="状态" value={filter()} onChange={(event) => { setFilter(event.currentTarget.value as JargonFilter); query(); }}>
            <option value="all">全部</option><option value="pending">待审</option><option value="confirmed">已确认</option><option value="unconfirmed">未确认</option>
          </Select>
          <Select label="范围" value={scope()} onChange={(event) => { setScope(event.currentTarget.value as JargonScope); query(); }}>
            <option value="all">全部范围</option><option value="global">全局</option><option value="local">本地</option>
          </Select>
          <Button icon="search" onClick={query}>查询</Button>
        </div>
        <div class={styles['batch-toolbar']}>
          <Badge>{`已选 ${formatCount(selected().size)}/${formatCount(items().length)}`}</Badge>
          <div class="inline-actions">
            <Button size="sm" onClick={() => setSelected(new Set(items().map((item) => String(item.id))))}>全选</Button>
            <Button size="sm" onClick={() => setSelected(new Set<string>())}>取消选择</Button>
            <Button size="sm" tone="success" onClick={() => batchAction('approve')}>批量确认</Button>
            <Button size="sm" tone="warning" onClick={() => batchAction('reject')}>批量驳回</Button>
            <Button size="sm" tone="danger" onClick={() => batchAction('delete')}>批量删除</Button>
          </div>
        </div>
        <div class="data-list">
          <For each={items()} fallback={<EmptyState title="没有匹配的黑话词条" />}>{(item) =>
            <article class="data-row">
              <Show when={editing() !== String(item.id)} fallback={
                <div class={styles['edit-grid']}>
                  <Input label="词条" value={draft().content} onInput={(event) => setDraft((current) => ({ ...current, content: event.currentTarget.value }))} />
                  <Textarea label="释义" value={draft().meaning} onInput={(event) => setDraft((current) => ({ ...current, meaning: event.currentTarget.value }))} />
                  <div class="inline-actions"><Button tone="success" onClick={() => save(String(item.id))}>保存</Button><Button onClick={cancel}>取消</Button></div>
                </div>
              }>
                <div class={styles['row-main']}>
                  <label class={styles['select-cell']} title="选择">
                    <input type="checkbox" aria-label="选择" checked={selected().has(String(item.id))} onChange={(event) => toggleSelect(String(item.id), event.currentTarget.checked)} />
                  </label>
                  <div class={styles['row-copy']}><strong>{textOrDash(item.content ?? item.jargon)}</strong><p>{textOrDash(item.meaning ?? item.definition)}</p><small>{formatTime(item.created_at)}</small></div>
                  <span class={styles['row-group']}>{textOrDash(item.group_id)}</span>
                  <Badge tone={jargonBadge(item).tone}>{jargonBadge(item).label}</Badge>
                  <Badge>{item.is_global ? '全局' : '本地'}</Badge>
                </div>
                <div class="inline-actions">
                  <Show when={!item.is_confirmed}><Button size="sm" tone="success" onClick={() => action(item, 'approve')}>确认</Button><Button size="sm" tone="warning" onClick={() => action(item, 'reject')}>驳回</Button></Show>
                  <Button size="sm" onClick={() => edit(item)}>编辑</Button>
                  <Button size="sm" onClick={() => action(item, 'toggle_global')}>{item.is_global ? '取消全局' : '设为全局'}</Button>
                  <Button size="sm" tone="danger" onClick={() => action(item, 'delete')}>删除</Button>
                </div>
              </Show>
            </article>
          }</For>
        </div>
        <Pagination page={page()} totalPages={totalPages()} disabled={loading()} onChange={(next) => { setPage(next); queueMicrotask(load); }} />
      </Panel>
    </div>
  );
}
