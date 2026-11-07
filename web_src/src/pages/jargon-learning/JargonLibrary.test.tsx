import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 黑话词库双端并集：读数卡、范围筛选、批量工具条、群组列 / 全局本地徽标与「设为全局 / 取消全局」。

const rows = [
  { id: 9, content: '摸鱼', meaning: '上班时间偷懒', is_confirmed: false, is_complete: false, is_global: false, group_id: 'g1', created_at: 1792500000 },
  { id: 10, content: 'yyds', meaning: '永远的神', is_confirmed: true, is_complete: true, is_global: true, group_id: null, created_at: 1792500000 },
];

const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('jargon library', () => {
  const listRequests: string[] = [];
  const posts: Array<{ url: string; body: unknown }> = [];

  beforeEach(() => {
    localStorage.clear();
    listRequests.length = 0;
    posts.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if ((init?.method ?? 'GET') !== 'GET') {
        posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return json({ success: true, message: '批量确认黑话完成：成功 2 条，失败 0 条' });
      }
      if (url.includes('/api/jargon/list') && url.includes('page_size=10')) {
        listRequests.push(url);
        return json({ success: true, jargon_list: rows, total: 2, page: 1, page_size: 10, total_pages: 1, data: rows });
      }
      if (url.includes('/api/jargon/stats')) return json({ total_candidates: 17, confirmed_jargon: 8, completed_inference: 5, active_groups: 2 });
      return json({});
    });
    window.location.hash = '#/jargon-learning';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows stats, group column, scope badges and state-dependent global toggles', async () => {
    render(() => <App />);
    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    expect(await screen.findByText('17')).toBeInTheDocument();
    expect(screen.getByText('活跃群组')).toBeInTheDocument();
    const first = screen.getByText('摸鱼').closest('article')!;
    expect(within(first).getByText('g1')).toBeInTheDocument();
    expect(within(first).getByText('本地')).toBeInTheDocument();
    expect(within(first).getByRole('button', { name: '设为全局' })).toBeInTheDocument();
    const second = screen.getByText('yyds').closest('article')!;
    expect(within(second).getByText('全局')).toBeInTheDocument();
    expect(within(second).getByRole('button', { name: '取消全局' })).toBeInTheDocument();
  });

  it('filters by scope from the first page', async () => {
    render(() => <App />);
    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('范围'), { target: { value: 'global' } });
    await waitFor(() => expect(listRequests.some((url) => url.includes('filter=global') && url.includes('page=1'))).toBe(true));
  });

  it('confirms batch actions on the selected entries', async () => {
    render(() => <App />);
    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '批量确认' }));
    expect(await screen.findByText('请先选择黑话条目')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '全选' }));
    expect(await screen.findByText('已选 2/2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '批量确认' }));
    expect(await screen.findByText('确定批量确认选中的 2 条黑话？')).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: '确认' }));
    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/jargon/batch_review'))).toBe(true));
    expect(posts.find((post) => post.url.includes('/api/jargon/batch_review'))?.body).toEqual({ jargon_ids: ['9', '10'], action: 'approve' });
    expect(await screen.findByText('批量确认黑话完成：成功 2 条，失败 0 条')).toBeInTheDocument();
  });
});
