import { cleanup, render, screen, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 「图谱详情」原为内嵌页独有面板，现移植到独立版：同位置（图谱视图右侧）、同文案。

vi.mock('../../components/business/GraphView', () => ({
  GraphView: () => <div data-testid="graph" />,
}));

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

const requested: string[] = [];

describe('graph details panel', () => {
  beforeEach(() => {
    localStorage.clear();
    requested.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      requested.push(url);
      if (url.includes('/api/graphs/memory')) {
        return json({
          type: 'memory',
          data_source: 'self_learning',
          groups: ['g1'],
          nodes: [
            { id: 'n1', name: '星门', category: 0, category_name: '概念', detail: '古代交通设施' },
            { id: 'n2', name: '遗迹', category: 1, category_name: '记忆' },
          ],
          links: [{ source: 'n1', target: 'n2' }],
          stats: { nodes: 2, links: 1, groups: 1 },
        });
      }
      return json({});
    });
    window.location.hash = '#/graphs';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows graph readouts and the first nodes next to the graph view', async () => {
    render(() => <App />);

    const title = await screen.findByText('图谱详情');
    const panel = title.closest('section')!;
    expect(await within(panel).findByText('星门')).toBeInTheDocument();
    expect(within(panel).getByText('古代交通设施')).toBeInTheDocument();
    expect(within(panel).getByText('概念')).toBeInTheDocument();
    expect(within(panel).getByText('self_learning')).toBeInTheDocument();
    for (const label of ['节点', '连线', '群组', '来源']) expect(within(panel).getByText(label)).toBeInTheDocument();
    // 与内嵌页一致：不再传 limit，由后端默认 120 个节点封顶
    expect(requested.find((url) => url.includes('/api/graphs/memory'))).not.toContain('limit=');
  });

  it('shows the compact empty state when the graph has no nodes', async () => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({}));
    render(() => <App />);

    const title = await screen.findByText('图谱详情');
    expect(await within(title.closest('section')!).findByText('暂无图谱节点')).toBeInTheDocument();
    expect(screen.getByText('图谱暂无节点')).toBeInTheDocument();
  });
});
