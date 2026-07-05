import * as echarts from 'echarts/core';
import type { EChartsOption } from 'echarts';
import { BarChart, GraphChart, LineChart, PieChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { createEffect, onCleanup, onMount } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import styles from './EChart.module.scss';

echarts.use([
  BarChart, GraphChart, LineChart, PieChart,
  GridComponent, LegendComponent, TitleComponent, TooltipComponent,
  CanvasRenderer,
]);

export function EChart(props: {
  option: EChartsOption;
  class?: string;
  onReady?: (chart: echarts.ECharts) => void;
}) {
  const dashboard = useDashboard();
  let element!: HTMLDivElement;
  let chart: echarts.ECharts | undefined;
  let observer: ResizeObserver | undefined;
  onMount(() => {
    chart = echarts.init(element, dashboard.theme());
    chart.setOption(props.option, true);
    props.onReady?.(chart);
    observer = new ResizeObserver(() => chart?.resize());
    observer.observe(element);
  });
  createEffect(() => {
    const nextTheme = dashboard.theme();
    if (!chart) return;
    const option = props.option;
    chart.dispose();
    chart = echarts.init(element, nextTheme);
    chart.setOption(option, true);
    props.onReady?.(chart);
  });
  createEffect(() => chart?.setOption(props.option, true));
  onCleanup(() => {
    observer?.disconnect();
    chart?.dispose();
  });
  return <div ref={element} class={`${styles['echart']} ${props.class || ''}`} role="img" />;
}
