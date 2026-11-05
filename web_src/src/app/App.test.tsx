import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
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
  'shadow-mode': '影子模式',
  emotion: '情绪中枢',
  content: '学习内容',
  graphs: '记忆 / 知识图谱',
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

  it.each([
    { tier: 'basic', label: '基础能力依赖', icon: 'bolt', mirror: 'default' },
    { tier: 'full', label: '全能力依赖', icon: 'extension', mirror: 'tsinghua' },
  ])('confirms and installs $tier dependencies with consistent button states', async ({ tier, label, icon, mirror }) => {
    vi.restoreAllMocks();
    const posts: unknown[] = [];
    let finishInstall!: (response: Response) => void;
    const installResponse = new Promise<Response>((resolve) => { finishInstall = resolve; });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === 'POST' && url.includes('/api/dependencies/install')) {
        posts.push(JSON.parse(String(init.body)));
        return installResponse;
      }
      const payload = url.includes('/api/config/schema')
        ? { groups: [{ label: '基础设置', fields: [] }] }
        : url.endsWith('/api/config')
          ? {}
          : {};
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    window.location.hash = '#/settings';
    render(() => <App />);
    expect(await screen.findByRole('heading', { name: '设置', level: 2 })).toBeInTheDocument();

    const installButton = screen.getByRole('button', { name: label });
    expect(installButton.querySelector('.material-icons')).toHaveTextContent(icon);
    await fireEvent.change(screen.getByLabelText('pip 镜像源'), { target: { value: mirror } });
    await fireEvent.click(installButton);
    expect(await screen.findByRole('heading', { name: '安装 Python 依赖', level: 2 })).toBeInTheDocument();
    expect(posts).toHaveLength(0);
    await fireEvent.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({
      manual_confirmed: true,
      source: 'webui_settings',
      tier,
      pip_mirror: mirror,
    });
    const installButtons = [
      screen.getByRole('button', { name: '基础能力依赖' }),
      screen.getByRole('button', { name: '全能力依赖' }),
    ];
    installButtons.forEach((button) => expect(button).toBeDisabled());
    finishInstall(new Response('{"message":"ok"}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await waitFor(() => installButtons.forEach((button) => expect(button).toBeEnabled()));
  });
});
