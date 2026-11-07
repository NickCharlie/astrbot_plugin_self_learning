import { cleanup, fireEvent, render, screen, within } from '@solidjs/testing-library';
import { createEffect } from 'solid-js';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

const { charts } = vi.hoisted(() => ({ charts: [] as unknown[] }));
vi.mock('../../components/charts/EChart', () => ({
  EChart: (props: { option: unknown }) => {
    createEffect(() => { charts.push(props.option); });
    return <div data-testid="echart" />;
  },
}));

// 表达方式学习双端并集：读数卡、表达样本库四分类、表达学习构成、学习模式三栏。

const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('expression learning page', () => {
  beforeEach(() => {
    localStorage.clear();
    charts.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/style_learning/content_text')) {
        return json({
          dialogues: [{ id: 1, title: 'Alice', text: 'Alice: 你好世界' }],
          analysis: [],
          features: [{ id: 2, title: '夸赞时' }],
          history: [{ id: 3, title: '首次学习' }, { id: 4, title: '第二次学习' }],
        });
      }
      if (url.includes('/api/style_learning/results')) {
        return json({ statistics: { unique_styles: 13, total_samples: 13, avg_confidence: 66.7, latest_update: null } });
      }
      if (url.includes('/api/style_learning/patterns')) {
        return json({ emotion_patterns: [{ name: '开心' }], language_patterns: [{ name: '短句' }, { pattern: '口癖' }], topic_patterns: [] });
      }
      return json({});
    });
    window.location.hash = '#/expression-learning';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows stats, samples, composition and pattern columns', async () => {
    render(() => <App />);
    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('查看表达统计与学习模式，以及对话样本、分析结果、风格特征与学习历史。')).toBeInTheDocument();
    expect(await screen.findByText('66.7')).toBeInTheDocument();
    expect(screen.getByText('最近更新').closest('.slx-stat')?.textContent).toContain('--');

    const patterns = screen.getByText('学习模式').closest('section')!;
    expect(within(patterns).getByText('开心')).toBeInTheDocument();
    expect(within(patterns).getByText('口癖')).toBeInTheDocument();
    expect(within(patterns).getByText('暂无模式')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '历史' }));
    expect(await screen.findByText('第二次学习')).toBeInTheDocument();

    const option = charts[charts.length - 1] as { series: Array<{ data: Array<{ name: string; value: number }> }> };
    expect(option.series[0].data).toEqual([
      { name: '对话', value: 1 },
      { name: '分析', value: 0 },
      { name: '特征', value: 1 },
      { name: '历史', value: 2 },
    ]);
  });
});
