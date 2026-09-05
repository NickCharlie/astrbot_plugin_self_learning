import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DashboardProvider } from '../../stores/dashboard';
import { replaceLocation } from '../../lib/navigation';
import { ConfirmDialog } from '../feedback/Feedback';
import { WebuiPasswordPanel } from './WebuiPasswordPanel';

vi.mock('../../lib/navigation', () => ({
  replaceLocation: vi.fn(),
}));

const jsonResponse = (payload: unknown, status = 200) =>
  new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });

const passwordStatus = (enabled: boolean) =>
  vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/password_status')) return jsonResponse({ password_enabled: enabled });
    return jsonResponse({});
  });

const fillField = async (label: string, value: string) => {
  await fireEvent.input(await screen.findByLabelText(label), { target: { value } });
};

describe('WebuiPasswordPanel', () => {
  beforeEach(() => {
    vi.mocked(replaceLocation).mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('hides itself when the password status is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({}, 500)));
    render(() => <DashboardProvider><WebuiPasswordPanel /></DashboardProvider>);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText('WebUI 访问密码')).toBeNull();
  });

  it('sets a custom password in passwordless mode after confirmation', async () => {
    const posts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if ((init?.method || 'GET').toUpperCase() === 'POST') {
        posts.push(JSON.parse(String(init?.body || '{}')));
        return jsonResponse({ success: true, message: 'ok', redirect: '/api/login' });
      }
      if (url.includes('/api/password_status')) return jsonResponse({ password_enabled: false });
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    render(() => <DashboardProvider><WebuiPasswordPanel /><ConfirmDialog /></DashboardProvider>);

    await fillField('自定义密码', 'CustomPass123!');
    await fillField('确认新密码', 'CustomPass123!');
    fireEvent.click(await screen.findByRole('button', { name: '设置并启用密码' }));

    expect(await screen.findByRole('heading', { name: '启用 WebUI 密码', level: 2 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ password: 'CustomPass123!', manual_confirmed: true });
    // 跳转有 900ms 延迟，轮询等待
    await vi.waitFor(() => expect(replaceLocation).toHaveBeenCalledWith('/api/login'), { timeout: 2000 });
  });

  it('rejects mismatched confirmation without posting', async () => {
    vi.stubGlobal('fetch', passwordStatus(false));
    render(() => <DashboardProvider><WebuiPasswordPanel /><ConfirmDialog /></DashboardProvider>);

    await fillField('自定义密码', 'CustomPass123!');
    await fillField('确认新密码', 'DifferentPass123!');
    fireEvent.click(await screen.findByRole('button', { name: '设置并启用密码' }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole('heading', { name: '启用 WebUI 密码', level: 2 })).toBeNull();
    expect(replaceLocation).not.toHaveBeenCalled();
  });

  it('changes password when protection is enabled and redirects to login', async () => {
    const posts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if ((init?.method || 'GET').toUpperCase() === 'POST') {
        posts.push(JSON.parse(String(init?.body || '{}')));
        return jsonResponse({ success: true, message: 'ok', redirect: '/api/login' });
      }
      if (url.includes('/api/password_status')) return jsonResponse({ password_enabled: true });
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    render(() => <DashboardProvider><WebuiPasswordPanel /><ConfirmDialog /></DashboardProvider>);

    await fillField('当前密码', 'OldPass123!');
    await fillField('新密码', 'NewPass456!');
    await fillField('确认新密码', 'NewPass456!');
    fireEvent.click(await screen.findByRole('button', { name: '修改密码' }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ old_password: 'OldPass123!', new_password: 'NewPass456!' });
    await vi.waitFor(() => expect(replaceLocation).toHaveBeenCalledWith('/api/login'), { timeout: 2000 });
  });
});
