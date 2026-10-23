import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// issue #274：黑话驳回后不再显示待审，首页待办与 AI 巡检与待审队列同源。

const pendingItem = (isComplete: boolean) => ({
  id: 7,
  content: '摸鱼',
  meaning: '上班时间偷懒',
  is_confirmed: false,
  // 驳回写 is_jargon=false；从未定论的候选保持 null
  is_jargon: isComplete ? false : null,
  is_complete: isComplete,
  created_at: 1792500000,
});

const json = (payload: Record<string, unknown>) => new Response(
  JSON.stringify({ success: true, ...payload }),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

describe('jargon rejected state and pending counts', () => {
  const state = {
    rejected: false,
    pendingTotal: 1,
    pendingGets: 0,
    reviewPosted: false,
    lastPendingGetAfterPost: false,
    holdMetrics: false,
  };
  let metricsGate = Promise.resolve();
  let releaseMetrics = () => {};

  const installFetch = () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      // 持住一个无关接口，模拟仪表盘首轮刷新尚未结束
      if (state.holdMetrics && url.includes('/api/metrics') && !url.includes('/trends')) {
        await metricsGate;
      }
      if (url.includes('/api/jargon/list')) {
        const isPendingQueue = url.includes('pending=true');
        if (isPendingQueue) {
          if (state.reviewPosted) state.lastPendingGetAfterPost = true;
          state.pendingGets += 1;
        }
        const isPageList = url.includes('page_size=10');
        const total = isPageList ? 1 : state.rejected ? 0 : state.pendingTotal;
        const rows = isPageList
          ? [pendingItem(state.rejected)]
          : total ? [pendingItem(false)] : [];
        const payload = isPageList
          ? { jargon_list: rows, total, page: 1, page_size: 10, total_pages: 1, data: rows }
          : { jargon_list: rows, total, data: rows };
        return new Response(JSON.stringify({ success: true, ...payload }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (method === 'POST' && url.includes('/api/jargon/7/review')) {
        state.reviewPosted = true;
        state.rejected = true;
        return new Response(JSON.stringify({ success: true, message: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/jargon/stats')) {
        // 已驳回词条计入 total_candidates 但不在待审队列：待办不应被它顶起来
        return new Response(
          JSON.stringify({ total_candidates: 1, confirmed_jargon: 0, completed_inference: 1 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
  };

  beforeEach(() => {
    localStorage.clear();
    state.rejected = false;
    state.pendingTotal = 1;
    state.pendingGets = 0;
    state.reviewPosted = false;
    state.lastPendingGetAfterPost = false;
    state.holdMetrics = false;
    metricsGate = Promise.resolve();
    releaseMetrics = () => {};
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('keeps the rejected candidate out of home backlog counts', async () => {
    state.pendingTotal = 0;
    installFetch();
    window.location.hash = '#/home';
    render(() => <App />);

    // stats 声称 total_candidates=1、confirmed=0（旧公式会得出待办 1），待审队列实际为空
    expect(await screen.findByText('队列已清空')).toBeInTheDocument();
    expect(screen.getByText('人格 0 · 风格 0 · 黑话 0')).toBeInTheDocument();
  });

  it('uses the pending queue total even when it exceeds the page size', async () => {
    installFetch();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/jargon/list') && url.includes('pending=true')) {
        return new Response(
          JSON.stringify({
            success: true,
            jargon_list: Array.from({ length: 5 }, (_, index) => ({ id: index })),
            total: 7,
            data: Array.from({ length: 5 }, (_, index) => ({ id: index })),
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    window.location.hash = '#/home';
    render(() => <App />);

    // 列表被 page_size=5 截断，但待审总数应为分页 total=7
    expect(await screen.findByText('人格 0 · 风格 0 · 黑话 7')).toBeInTheDocument();
  });

  it('feeds the AI insights backlog from the same pending queue total', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/jargon/list') && url.includes('pending=true')) {
        return new Response(
          JSON.stringify({ success: true, jargon_list: [], total: 7, data: [] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    window.location.hash = '#/insights';
    render(() => <App />);

    expect(await screen.findByText('当前约 7 条记录等待处理。')).toBeInTheDocument();
  });

  it('labels inference-completed candidates as finished rather than rejected', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/jargon/list') && url.includes('page_size=10')) {
        // 推断/导入已结束但 is_jargon 未定论：不是人工驳回
        const row = { id: 9, content: '绝绝子', is_confirmed: false, is_jargon: null, is_complete: true };
        return json({ jargon_list: [row], total: 1, data: [row] });
      }
      return json({});
    });
    window.location.hash = '#/jargon-learning';
    render(() => <App />);

    expect(await screen.findByText('绝绝子')).toBeInTheDocument();
    expect(document.querySelector('article .slx-badge')?.textContent).toBe('已完成');
  });

  it('refreshes the shared snapshot even while an earlier dashboard load is in flight', async () => {
    state.holdMetrics = true;
    metricsGate = new Promise<void>((resolve) => { releaseMetrics = resolve; });
    installFetch();
    window.location.hash = '#/jargon-learning';
    render(() => <App />);

    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    const pendingGetsBefore = state.pendingGets;
    fireEvent.click(screen.getByRole('button', { name: '驳回' }));

    // 首轮刷新还卡着时，审查后的 refresh 仍必须重新拉取待审队列
    await waitFor(() => expect(state.pendingGets).toBeGreaterThan(pendingGetsBefore));
    releaseMetrics();
  });

  it('shows the rejected badge and refreshes the global snapshot after rejecting', async () => {
    installFetch();
    window.location.hash = '#/jargon-learning';
    render(() => <App />);

    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    // 状态徽标与筛选下拉里的「待审」同名，直接取待审行内的徽标
    const badge = () => document.querySelector('article .slx-badge')?.textContent;
    expect(badge()).toBe('待审');
    const pendingGetsBefore = state.pendingGets;

    fireEvent.click(screen.getByRole('button', { name: '驳回' }));

    await waitFor(() => expect(badge()).toBe('已驳回'));
    expect(state.reviewPosted).toBe(true);
    // 审查动作后必须同步刷新全局快照（重新请求待审队列），而不是等定时刷新
    expect(state.lastPendingGetAfterPost).toBe(true);
    expect(state.pendingGets).toBeGreaterThan(pendingGetsBefore);
  });
});
