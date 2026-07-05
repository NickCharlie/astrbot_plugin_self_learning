import type { EChartsOption } from 'echarts';
import { createMemo, createSignal, For, onMount } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object } from '../shared';
import { summarize, textOrDash } from '../../lib/format';
import { EChart } from '../../components/charts/EChart';
import { PageHeader } from '../../components/layout/PageHeader';
import { EmptyState, Panel, SegmentedControl } from '../../components/ui';
import styles from './ExpressionLearningPage.module.scss';

type Bucket = 'dialogues' | 'analysis' | 'features' | 'history';

export function ExpressionLearningPage() {
  const dashboard = useDashboard();
  const [bucket, setBucket] = createSignal<Bucket>('dialogues');
  const [payload, setPayload] = createSignal<Record<string, unknown>>({});
  const load = async () => {
    try { setPayload(await api.get('/api/style_learning/content_text')); }
    catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '表达内容加载失败', 'danger'); }
  };
  onMount(load);
  const items = () => {
    const root = object(payload());
    const nested = object(root.data);
    return list<Record<string, unknown>>(root[bucket()] ?? nested[bucket()]);
  };
  const chart = createMemo<EChartsOption>(() => {
    const root = object(payload());
    const labels = ['dialogues', 'analysis', 'features', 'history'];
    return {
      tooltip: { trigger: 'item' },
      series: [{ type: 'pie', radius: ['50%', '76%'], data: labels.map((name) => ({ name, value: list(object(root)[name]).length })) }],
    };
  });
  return (
    <div class="page">
      <PageHeader title="表达方式学习" description="查看对话样本、分析结果、风格特征与学习历史。" icon="record_voice_over" />
      <div class="two-column">
        <Panel title="表达样本库" actions={<SegmentedControl value={bucket()} onChange={setBucket} options={[
          { value: 'dialogues', label: '对话' }, { value: 'analysis', label: '分析' }, { value: 'features', label: '特征' }, { value: 'history', label: '历史' },
        ]} />}>
          <div class={styles['content-list']}>
            <For each={items().slice(0, 20)} fallback={<EmptyState />}>{(item) =>
              <details><summary>{textOrDash(item.title ?? item.name ?? item.id ?? '内容项')}</summary><pre>{summarize(item)}</pre></details>
            }</For>
          </div>
        </Panel>
        <Panel title="表达学习构成"><EChart option={chart()} class="chart-lg" /></Panel>
      </div>
    </div>
  );
}
