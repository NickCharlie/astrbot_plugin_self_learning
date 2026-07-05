import type { EChartsOption } from 'echarts';
import { createMemo } from 'solid-js';
import type { GraphPayload } from '../../types/dashboard';
import { EChart } from '../charts/EChart';
import styles from './GraphView.module.scss';

const positionCache = new Map<string, [number, number]>();
export const graphHash = (value: string) => {
  let hash = 2166136261;
  for (const char of value) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return hash >>> 0;
};

export function stableGraphPoint(id: string, index: number, total: number): [number, number] {
  const cached = positionCache.get(id);
  if (cached) return cached;
  const phase = (graphHash(id) % 628) / 100;
  const angle = (index / Math.max(total, 1)) * Math.PI * 2 + phase;
  const radius = 180 + (graphHash(`${id}:radius`) % 160);
  const point: [number, number] = [480 + Math.cos(angle) * radius, 320 + Math.sin(angle) * radius];
  positionCache.set(id, point);
  return point;
}

export function GraphView(props: { payload: GraphPayload; layout: 'force' | 'circular' }) {
  const option = createMemo<EChartsOption>(() => {
    const nodes = props.payload.nodes || [];
    const links = props.payload.links || props.payload.edges || [];
    return {
      animationDurationUpdate: 300,
      tooltip: { trigger: 'item' },
      series: [{
        type: 'graph',
        layout: props.layout === 'circular' ? 'circular' : 'none',
        roam: true,
        draggable: true,
        symbolSize: (value: unknown) => 22 + Math.min(28, Number(value) || 0),
        label: { show: true, position: 'right', formatter: '{b}' },
        lineStyle: { opacity: .5, curveness: .08 },
        data: nodes.map((node, index) => {
          const id = String(node.id ?? node.name ?? index);
          const point = stableGraphPoint(id, index, nodes.length);
          return {
            id, name: String(node.name ?? node.label ?? id),
            value: node.value ?? 1,
            category: node.category,
            ...(props.layout === 'force' ? { x: point[0], y: point[1] } : {}),
          };
        }),
        links,
        categories: props.payload.categories,
      }],
    } as EChartsOption;
  });
  return <EChart class={styles['graph-chart']} option={option()} onReady={(chart) => {
    chart.on('mouseup', (params) => {
      if (params.dataType !== 'node' || !params.data || typeof params.data !== 'object') return;
      const node = params.data as { id?: string; x?: number; y?: number };
      if (node.id && Number.isFinite(node.x) && Number.isFinite(node.y)) positionCache.set(node.id, [node.x!, node.y!]);
    });
  }} />;
}
