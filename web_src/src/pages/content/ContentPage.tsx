import { createSignal, For, onMount } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object } from '../shared';
import { summarize, textOrDash } from '../../lib/format';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, EmptyState, Input, Panel, SegmentedControl } from '../../components/ui';
import styles from './ContentPage.module.scss';

type Bucket = 'dialogues' | 'analysis' | 'features' | 'history';

export function ContentPage() {
  const dashboard = useDashboard();
  const [bucket, setBucket] = createSignal<Bucket>('dialogues');
  const [query, setQuery] = createSignal('');
  const [payload, setPayload] = createSignal<Record<string, unknown>>({});
  const [loading, setLoading] = createSignal(false);
  const load = async () => {
    setLoading(true);
    try { setPayload(await api.get('/api/style_learning/content_text')); }
    catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '学习内容加载失败', 'danger'); }
    finally { setLoading(false); }
  };
  onMount(load);
  const items = () => list<Record<string, unknown>>(object(payload())[bucket()] ?? object(object(payload()).data)[bucket()])
    .filter((item) => !query() || summarize(item).toLowerCase().includes(query().toLowerCase()));
  const remove = async (item: Record<string, unknown>) => {
    const id = String(item.id ?? item.uuid ?? '');
    if (!id || !await dashboard.confirm({ title: '删除学习内容', message: '删除后不可撤销，确定继续吗？', tone: 'danger' })) return;
    try {
      await api.delete(`/api/style_learning/content_text/${encodeURIComponent(bucket())}/${encodeURIComponent(id)}`);
      dashboard.toast('学习内容已删除', 'success'); await load();
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '删除失败', 'danger'); }
  };
  return (
    <div class="page">
      <PageHeader title="学习内容" description="按内容类型浏览、检索和清理表达学习数据。" icon="library_books" />
      <Panel title="内容浏览器" actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>}>
        <div class={styles['content-toolbar']}>
          <SegmentedControl value={bucket()} onChange={setBucket} options={[
            { value: 'dialogues', label: '对话' }, { value: 'analysis', label: '分析' }, { value: 'features', label: '特征' }, { value: 'history', label: '历史' },
          ]} />
          <Input placeholder="搜索当前分类" value={query()} onInput={(event) => setQuery(event.currentTarget.value)} />
        </div>
        <div class={styles['content-grid']}>
          <For each={items()} fallback={<EmptyState title="当前分类暂无内容" />}>{(item) =>
            <details class={styles['content-item']}>
              <summary><strong>{textOrDash(item.title ?? item.name ?? item.id ?? '内容项')}</strong><span class="material-icons">expand_more</span></summary>
              <pre>{summarize(item)}</pre>
              <Button size="sm" tone="danger" icon="delete" onClick={() => remove(item)}>删除</Button>
            </details>
          }</For>
        </div>
      </Panel>
    </div>
  );
}
