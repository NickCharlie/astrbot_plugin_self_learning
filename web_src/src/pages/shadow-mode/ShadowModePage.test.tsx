import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 影子模式双端一致：生效群组默认跟随来源群组（手动改过则保留）、档案计数、学习后保留当前选择。

const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

const status = {
  profiles: [{ id: 1, target_group_id: 'imp1', source_type: 'imported', source_group_id: 'imp1', sender_id: 'u1', sender_name: 'Bob', sender_qq: '123', sample_count: 30, enabled: true, updated_at: 1792500000 }],
  minimum_samples: 5,
  sources: { live: [], imported: [{ group_id: 'imp1', member_count: 4 }, { group_id: 'imp2', member_count: 2 }] },
};

describe('shadow mode page', () => {
  const posts: Array<{ url: string; body: unknown }> = [];

  beforeEach(() => {
    localStorage.clear();
    posts.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if ((init?.method ?? 'GET') !== 'GET') {
        posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return json({ success: true });
      }
      if (url.includes('/api/shadow-mode/candidates')) {
        return json({ success: true, data: { candidates: [{ sender_id: 'u2', sender_name: 'Carol', sender_qq: '456', message_count: 42, ready: true }], minimum_samples: 5 } });
      }
      if (url.includes('/api/shadow-mode')) return json({ success: true, data: status });
      return json({});
    });
    window.location.hash = '#/shadow-mode';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('lets the target group follow the source group unless it was edited', async () => {
    render(() => <App />);
    expect(await screen.findByText('Carol')).toBeInTheDocument();
    expect(screen.getByText('至少需要 5 条有效文本')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('条消息')).toBeInTheDocument();
    const target = screen.getByLabelText('生效群组') as HTMLInputElement;
    expect(target.value).toBe('imp1');

    fireEvent.change(screen.getByLabelText('来源群组'), { target: { value: 'imp2' } });
    await waitFor(() => expect(target.value).toBe('imp2'));

    fireEvent.input(target, { target: { value: 'custom-group' } });
    fireEvent.change(screen.getByLabelText('来源群组'), { target: { value: 'imp1' } });
    await waitFor(() => expect((screen.getByLabelText('来源群组') as HTMLSelectElement).value).toBe('imp1'));
    expect(target.value).toBe('custom-group');
  });

  it('keeps the current source and group after learning', async () => {
    render(() => <App />);
    expect(await screen.findByText('Carol')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('来源群组'), { target: { value: 'imp2' } });
    await waitFor(() => expect((screen.getByLabelText('生效群组') as HTMLInputElement).value).toBe('imp2'));
    fireEvent.click(await screen.findByText('Carol'));
    fireEvent.click(screen.getByRole('button', { name: '学习并启用' }));
    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/shadow-mode/profiles'))).toBe(true));
    expect(await screen.findByText('已学习并启用 Carol 的影子模式')).toBeInTheDocument();
    await waitFor(() => expect((screen.getByLabelText('来源群组') as HTMLSelectElement).value).toBe('imp2'));
  });
});
