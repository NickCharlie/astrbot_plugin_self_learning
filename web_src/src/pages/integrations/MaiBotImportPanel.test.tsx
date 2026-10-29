import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 后端 /api/integrations/maibot-learning/* 此前没有 WebUI 入口。

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

let previewPayload: Record<string, unknown> | null = null;

const installFetch = () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method === 'POST' && url.includes('/api/integrations/maibot-learning/preview')) {
      previewPayload = JSON.parse(String(init?.body ?? '{}'));
      return json({ success: true, data: { counts: { expressions: 2, jargons: 1, memories: 3 } } });
    }
    if (url.includes('/api/integrations/worldbook/imports')) return json({ imports: [] });
    return json({});
  });
};

describe('maibot learning import panel', () => {
  beforeEach(() => {
    localStorage.clear();
    previewPayload = null;
    installFetch();
    window.location.hash = '#/integrations';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('previews MaiBot learning data from a pasted export payload', async () => {
    render(() => <App />);

    const heading = await screen.findByText('MaiBot 学习数据');
    const panel = heading.closest('section');
    expect(panel).not.toBeNull();
    const textarea = within(panel!).getByPlaceholderText(/\{"version": 1/);
    fireEvent.input(textarea, {
      target: { value: JSON.stringify({ version: 1, sessions: [], expressions: [], jargons: [], memories: [] }) },
    });
    fireEvent.click(within(panel!).getByRole('button', { name: '预览' }));

    await waitFor(() => expect(previewPayload?.payload).toEqual({ version: 1, sessions: [], expressions: [], jargons: [], memories: [] }));
    expect(await within(panel!).findByText(/counts/)).toBeInTheDocument();
  });
});
