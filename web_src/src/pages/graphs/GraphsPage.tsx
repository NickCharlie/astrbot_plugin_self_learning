import { createSignal, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { GraphPayload } from '../../types/dashboard';
import { object } from '../shared';
import { GraphView } from '../../components/business/GraphView';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, EmptyState, Input, Panel, SegmentedControl } from '../../components/ui';
import styles from './GraphsPage.module.scss';

type GraphType = 'memory' | 'knowledge';
type Layout = 'force' | 'circular';

export function GraphsPage() {
  const dashboard = useDashboard();
  const [type, setType] = createSignal<GraphType>('memory');
  const [layout, setLayout] = createSignal<Layout>('force');
  const [groupId, setGroupId] = createSignal('');
  const [payload, setPayload] = createSignal<GraphPayload>({});
  const [loading, setLoading] = createSignal(false);
  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (groupId().trim()) params.set('group_id', groupId().trim());
      setPayload(await api.get(`/api/graphs/${type()}?${params}`));
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '图谱加载失败', 'danger'); }
    finally { setLoading(false); }
  };
  onMount(load);
  const hasNodes = () => Array.isArray(object(payload()).nodes) && (object(payload()).nodes as unknown[]).length > 0;
  return (
    <div class="page">
      <PageHeader title="记忆 / 知识图谱" description="探索记忆节点、知识实体及其关系；拖动位置会在本次会话中保留。" icon="hub" />
      <Panel title="图谱视图" hint="稳定静态布局避免每次刷新后节点重新飞散" actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>}>
        <div class={styles['graph-toolbar']}>
          <SegmentedControl value={type()} onChange={(next) => { setType(next); queueMicrotask(load); }} options={[{ value: 'memory', label: '记忆图谱' }, { value: 'knowledge', label: '知识图谱' }]} />
          <SegmentedControl value={layout()} onChange={setLayout} options={[{ value: 'force', label: '稳定布局' }, { value: 'circular', label: '环形布局' }]} />
          <Input placeholder="群组 ID（可选）" value={groupId()} onInput={(event) => setGroupId(event.currentTarget.value)} onKeyDown={(event) => event.key === 'Enter' && load()} />
        </div>
        <Show when={hasNodes()} fallback={<EmptyState title="图谱暂无节点" detail="可尝试清空群组筛选后刷新。" />}>
          <GraphView payload={payload()} layout={layout()} />
        </Show>
      </Panel>
    </div>
  );
}
