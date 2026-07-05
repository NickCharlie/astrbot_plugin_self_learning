import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { JargonItem, Paginated } from '../../types/dashboard';
import { list } from '../shared';
import { formatTime, textOrDash } from '../../lib/format';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge, Button, EmptyState, Input, Pagination, Panel, Select, Textarea } from '../../components/ui';
import styles from './JargonLearningPage.module.scss';

type JargonFilter = 'all' | 'pending' | 'confirmed' | 'unconfirmed';

export function buildJargonListParams(input: {
  page: number;
  pageSize: number;
  filter: JargonFilter;
  search: string;
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
  return params;
}

export function JargonLearningPage() {
  const dashboard = useDashboard();
  const [items, setItems] = createSignal<JargonItem[]>([]);
  const [page, setPage] = createSignal(1);
  const [totalPages, setTotalPages] = createSignal(1);
  const [filter, setFilter] = createSignal<JargonFilter>('all');
  const [search, setSearch] = createSignal('');
  const [loading, setLoading] = createSignal(false);
  const [editing, setEditing] = createSignal<string | null>(null);
  const [draft, setDraft] = createSignal({ content: '', meaning: '' });
  const load = async () => {
    setLoading(true);
    try {
      const params = buildJargonListParams({ page: page(), pageSize: 10, filter: filter(), search: search() });
      const payload = await api.get<Paginated<JargonItem>>(`/api/jargon/list?${params}`);
      const rows = list<JargonItem>(payload);
      setItems(rows);
      setTotalPages(Math.max(1, Number(payload.total_pages ?? Math.ceil(Number(payload.total ?? rows.length) / 10))));
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '黑话加载失败', 'danger'); }
    finally { setLoading(false); }
  };
  onMount(load);
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
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '操作失败', 'danger'); }
  };
  return (
    <div class="page">
      <PageHeader title="黑话学习" description="检索、编辑和审查从群聊语境中学习到的词条。" icon="forum" />
      <Panel title="黑话词库" hint="支持分页、状态筛选和原地编辑" actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>}>
        <div class={styles['filter-bar']}>
          <Input label="搜索" placeholder="词条或释义" value={search()} onInput={(event) => setSearch(event.currentTarget.value)} onKeyDown={(event) => event.key === 'Enter' && load()} />
          <Select label="状态" value={filter()} onChange={(event) => { setFilter(event.currentTarget.value as JargonFilter); setPage(1); queueMicrotask(load); }}>
            <option value="all">全部</option><option value="pending">待审</option><option value="confirmed">已确认</option><option value="unconfirmed">未确认</option>
          </Select>
          <Button icon="search" onClick={load}>查询</Button>
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
                <div class="data-row-main">
                  <div><strong>{textOrDash(item.content ?? item.jargon)}</strong><p>{textOrDash(item.meaning ?? item.definition)}</p><small>{formatTime(item.created_at)}</small></div>
                  <Badge tone={item.is_confirmed ? 'success' : 'warning'}>{item.is_confirmed ? '已确认' : textOrDash(item.status ?? '待审')}</Badge>
                </div>
                <div class="inline-actions">
                  <Show when={!item.is_confirmed}><Button size="sm" tone="success" onClick={() => action(item, 'approve')}>确认</Button><Button size="sm" tone="warning" onClick={() => action(item, 'reject')}>驳回</Button></Show>
                  <Button size="sm" onClick={() => edit(item)}>编辑</Button>
                  <Button size="sm" onClick={() => action(item, 'toggle_global')}>切换全局</Button>
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
