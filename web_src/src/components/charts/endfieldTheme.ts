// endfield 图表主题：中性灰阶主导，信号黄为首序列，状态绿只给在线/正向数据。
// 轴线/分割线沿用 1px 规则线语言；tooltip 为方角 ink 坞站；数值用等宽表格数字。
import * as echarts from 'echarts/core';

const MONO = '"IBM Plex Mono", "SFMono-Regular", ui-monospace, Consolas, monospace';
const UI = 'Inter, "Microsoft YaHei", "PingFang SC", "Noto Sans SC", system-ui, sans-serif';

function buildTheme(mode: 'light' | 'dark') {
  const light = mode === 'light';
  const ink = '#191919';
  const paper = '#f2f2f0';
  const text = light ? ink : paper;
  const muted = light ? '#63635e' : '#94948d';
  const rule = light ? 'rgba(25, 25, 25, 0.14)' : 'rgba(242, 242, 240, 0.12)';
  const ruleStrong = light ? 'rgba(25, 25, 25, 0.42)' : 'rgba(242, 242, 240, 0.38)';
  // 纸面上纯黄线条不可读：亮色主题首序列用 ink，黄作第二序列并加深一档
  const palette = light
    ? ['#191919', '#d9c800', '#7a7a74', '#0b9d6e', '#b4b4ae', '#4a4a46', '#a88f00', '#3f7a66']
    : ['#fffa00', '#f2f2f0', '#00ffa2', '#9a9a94', '#c8c400', '#5f5f5a', '#7fd9b7', '#d6d6d0'];

  const axis = {
    axisLine: { show: true, lineStyle: { color: ruleStrong, width: 1 } },
    axisTick: { show: true, lineStyle: { color: ruleStrong } },
    axisLabel: { color: muted, fontFamily: MONO, fontSize: 10.5 },
    splitLine: { show: true, lineStyle: { color: rule, width: 1, type: 'solid' } },
    splitArea: { show: false },
    nameTextStyle: { color: muted, fontFamily: MONO, fontSize: 10.5 },
  };

  return {
    color: palette,
    backgroundColor: 'transparent',
    textStyle: { color: text, fontFamily: UI },
    title: {
      textStyle: { color: text, fontFamily: UI, fontWeight: 700, fontSize: 13 },
      subtextStyle: { color: muted, fontFamily: MONO },
    },
    legend: {
      textStyle: { color: muted, fontFamily: UI, fontSize: 12 },
      icon: 'rect',
      itemWidth: 12,
      itemHeight: 6,
    },
    tooltip: {
      backgroundColor: light ? ink : paper,
      borderColor: light ? ink : paper,
      borderWidth: 0,
      borderRadius: 0,
      padding: [8, 10],
      textStyle: { color: light ? paper : ink, fontFamily: UI, fontSize: 12 },
      axisPointer: {
        lineStyle: { color: '#fffa00', width: 1 },
        crossStyle: { color: ruleStrong },
      },
    },
    categoryAxis: axis,
    valueAxis: axis,
    logAxis: axis,
    timeAxis: axis,
    line: {
      symbol: 'rect',
      symbolSize: 5,
      smooth: false,
      lineStyle: { width: 2 },
    },
    bar: {
      itemStyle: { borderRadius: 0 },
    },
    pie: {
      itemStyle: { borderColor: light ? '#f7f7f4' : '#1a1a1a', borderWidth: 2, borderRadius: 0 },
    },
    graph: {
      lineStyle: { color: ruleStrong, width: 1 },
      label: { color: text, fontFamily: UI },
    },
  };
}

let registered = false;

export function ensureEndfieldChartThemes() {
  if (registered) return;
  echarts.registerTheme('endfield-light', buildTheme('light'));
  echarts.registerTheme('endfield-dark', buildTheme('dark'));
  registered = true;
}

export function endfieldChartTheme(theme: string) {
  ensureEndfieldChartThemes();
  return theme === 'dark' ? 'endfield-dark' : 'endfield-light';
}
