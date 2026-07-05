import { cleanup, fireEvent, render, screen } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DASHBOARD_PAGES } from '../lib/routing';
import { App } from './App';

vi.mock('../components/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}));
vi.mock('../components/business/GraphView', () => ({
  GraphView: () => <div data-testid="graph" />,
}));

const headings: Record<string, string> = {
  home: '学习模块控制台',
  overview: '总览',
  insights: 'AI 巡检',
  monitoring: '运行监控',
  reviews: '审查队列',
  'jargon-learning': '黑话学习',
  'expression-learning': '表达方式学习',
  'persona-learning': '人格学习',
  content: '学习内容',
  graphs: '记忆 / 知识图谱',
  'reply-strategy': '回复策略',
  integrations: '功能融合',
  settings: '设置',
};

describe('dashboard page smoke tests', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  for (const page of DASHBOARD_PAGES) {
    it(`renders ${page}`, async () => {
      window.location.hash = `#/${page}`;
      render(() => <App />);
      expect(await screen.findByRole('heading', { name: headings[page], level: 2 })).toBeInTheDocument();
    });
  }

  it('returns home when the brand is clicked', async () => {
    window.location.hash = '#/overview';
    render(() => <App />);
    expect(await screen.findByRole('heading', { name: '总览', level: 2 })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('link', { name: '返回模块入口' }));
    expect(await screen.findByRole('heading', { name: '学习模块控制台', level: 2 })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/home');
  });

  it('renders system entry status from real API response shapes', async () => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      const payload = url.includes('/api/metrics/trends') ? { recent_batches: [{ id: 1 }] }
        : url.endsWith('/api/metrics') ? {
          total_messages_collected: 2216,
          filtered_messages: 2061,
          learning_efficiency: 73.3,
          llm_call_summary: { total_calls: 1, abnormal_provider_count: 0 },
        }
        : url.includes('/api/monitoring/health') ? { overall: 'healthy', checks: {} }
        : url.includes('/api/persona_updates/reviewed') ? { total: 4, updates: [] }
        : url.includes('/api/persona_updates') ? { total: 2, updates: [] }
        : url.includes('/api/style_learning/reviews') ? { total: 3, reviews: [] }
        : url.includes('/api/jargon/stats') ? { total_candidates: 17, confirmed_jargon: 8 }
        : url.includes('/api/data/statistics') ? { data: { style_learning: 2, memory: 1, knowledge_graph: 0 } }
        : url.includes('/api/integrations/status') ? {
          dashboards: [
            { id: 'self_learning', active: true, dashboard: { available: true } },
            { id: 'group_chat_plus', active: false, delegated: false, dashboard: { available: false } },
          ],
        }
        : url.includes('/api/config/schema') ? { groups: [{ fields: [{ key: 'one', editable: true }] }] }
        : {};
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    window.location.hash = '#/home';
    render(() => <App />);
    expect((await screen.findAllByText('73%')).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('2,216 条消息 · 筛选率 93%')).toBeInTheDocument();
    expect(screen.getByText('系统健康')).toBeInTheDocument();
    expect(screen.getByText('System Entry Points')).toBeInTheDocument();
  });
});
