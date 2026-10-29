import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 后端 /api/social_relations/* 此前没有 WebUI 入口，现补到图谱页第三视图。

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

let analyzeCalls = 0;

const installFetch = () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method === 'POST' && url.includes('/api/social_relations/g1/analyze')) {
      analyzeCalls += 1;
      return json({ success: true, message: '分析完成' });
    }
    if (url.includes('/api/social_relations/groups')) {
      return json({ success: true, groups: [{ group_id: 'g1', group_name: '测试群' }] });
    }
    if (url.includes('/api/social_relations/g1')) {
      return json({
        success: true,
        group_id: 'g1',
        members: [
          { user_id: 'u1', nickname: '小明', message_count: 5 },
          { user_id: 'u2', nickname: '小红', message_count: 3 },
        ],
        relations: [{ source: 'u1', target: 'u2', strength: 0.8 }],
        member_count: 2,
        relation_count: 1,
        message_count: 8,
      });
    }
    return json({});
  });
};

describe('social relations graph view', () => {
  beforeEach(() => {
    localStorage.clear();
    analyzeCalls = 0;
    installFetch();
    window.location.hash = '#/graphs';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('loads social relations as a graph and can trigger analysis', async () => {
    render(() => <App />);

    fireEvent.click(screen.getByRole('button', { name: '社交关系' }));
    const select = await screen.findByRole('combobox');
    await waitFor(() => expect(select).toHaveValue('g1'));
    const panel = screen.getByText('图谱视图').closest('section');
    expect(panel).not.toBeNull();
    fireEvent.click(within(panel!).getByRole('button', { name: '刷新' }));

    expect(await screen.findByText('成员 2 · 关系 1 · 消息 8')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重新分析' }));
    fireEvent.click(await screen.findByRole('button', { name: '开始分析' }));
    await waitFor(() => expect(analyzeCalls).toBe(1));
  });
});
