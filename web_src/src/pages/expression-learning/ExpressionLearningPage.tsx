import type { EChartsOption } from 'echarts';
import { createMemo, createSignal, For, onMount } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object } from '../shared';
import { formatCount, formatScore, formatTime, summarize, textOrDash } from '../../lib/format';
import { EChart } from '../../components/charts/EChart';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge, EmptyState, Panel, SegmentedControl, StatCard } from '../../components/ui';
import styles from './ExpressionLearningPage.module.scss';

type Bucket = 'dialogues' | 'analysis' | 'features' | 'history';

const BUCKETS: Array<{ value: Bucket; label: string }> = [
  { value: 'dialogues', label: '对话' },
  { value: 'analysis', label: '分析' },
  { value: 'features', label: '特征' },
  { value: 'history', label: '历史' },
];

const patternName = (item: unknown): string => {
  const record = object(item);
  return String(record.name || record.pattern || record.text || '');
};

export function ExpressionLearningPage() {
  const dashboard = useDashboard();
  const [bucket, setBucket] = createSignal<Bucket>('dialogues');
  const [payload, setPayload] = createSignal<Record<string, unknown>>({});
  const [results, setResults] = createSignal<Record<string, unknown>>({});
  const [patterns, setPatterns] = createSignal<Record<string, unknown>>({});
  // 读数（/style_learning/results）与学习模式（/style_learning/patterns）与内嵌插件页 page/style 同源
  const load = async () => {
    const [content, stats, learned] = await Promise.allSettled([
      api.get<Record<string, unknown>>('/api/style_learning/content_text'),
      api.get<Record<string, unknown>>('/api/style_learning/results'),
      api.get<Record<string, unknown>>('/api/style_learning/patterns'),
    ]);
    if (content.status === 'fulfilled') setPayload(content.value);
    else dashboard.toast(content.reason instanceof Error ? content.reason.message : '表达内容加载失败', 'danger');
    if (stats.status === 'fulfilled') setResults(object(stats.value));
    if (learned.status === 'fulfilled') setPatterns(object(learned.value));
  };
  onMount(load);
  const statistics = () => object(results().statistics);
  const items = () => {
    const root = object(payload());
    const nested = object(root.data);
    return list<Record<string, unknown>>(root[bucket()] ?? nested[bucket()]);
  };
  const chart = createMemo<EChartsOption>(() => {
    const root = object(payload());
    return {
      tooltip: { trigger: 'item' },
      series: [{ type: 'pie', radius: ['50%', '76%'], data: BUCKETS.map((item) => ({ name: item.label, value: list(root[item.value]).length })) }],
    };
  });
  const patternGroups = () => {
    const source = patterns();
    return [
      { title: '情绪模式', rows: list<unknown>(source.emotion_patterns) },
      { title: '语言模式', rows: list<unknown>(source.language_patterns) },
      { title: '话题模式', rows: list<unknown>(source.topic_patterns) },
    ];
  };
  return (
    <div class="page">
      <PageHeader title="表达方式学习" description="查看表达统计与学习模式，以及对话样本、分析结果、风格特征与学习历史。" icon="record_voice_over" />
      <div class="metrics-grid">
        <StatCard label="风格样本" value={formatCount(statistics().unique_styles || statistics().total_samples)} />
        <StatCard label="平均置信度" value={formatScore(statistics().avg_confidence)} />
        <StatCard label="总样本" value={formatCount(statistics().total_samples)} />
        <StatCard label="最近更新" value={statistics().latest_update ? formatTime(statistics().latest_update) : '--'} />
      </div>
      <div class="two-column">
        <Panel title="表达样本库" actions={<SegmentedControl label="表达样本库" value={bucket()} onChange={setBucket} options={BUCKETS} />}>
          <div class={styles['content-list']}>
            <For each={items().slice(0, 20)} fallback={<EmptyState />}>{(item) =>
              <details><summary>{textOrDash(item.title ?? item.name ?? item.id ?? '内容项')}</summary><pre>{summarize(item)}</pre></details>
            }</For>
          </div>
        </Panel>
        <Panel title="表达学习构成"><EChart option={chart()} class="chart-lg" /></Panel>
      </div>
      <Panel title="学习模式">
        <div class={styles['pattern-columns']}>
          <For each={patternGroups()}>{(group) =>
            <div class={styles['pattern-column']}>
              <h4><span>{group.title}</span><Badge>{formatCount(group.rows.length)}</Badge></h4>
              <For each={group.rows.slice(0, 12)} fallback={<EmptyState title="暂无模式" />}>{(item) =>
                <span class={styles['pattern-chip']}>{patternName(item)}</span>
              }</For>
            </div>
          }</For>
        </div>
      </Panel>
    </div>
  );
}
