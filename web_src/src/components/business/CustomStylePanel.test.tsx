import { cleanup, fireEvent, render, screen } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DashboardProvider } from '../../stores/dashboard';
import { reloadPage, replaceLocation } from '../../lib/navigation';
import { ConfirmDialog } from '../feedback/Feedback';
import { CustomStylePanel } from './CustomStylePanel';

vi.mock('../../lib/navigation', () => ({
  replaceLocation: vi.fn(),
  reloadPage: vi.fn(),
}));

describe('CustomStylePanel', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(replaceLocation).mockClear();
    vi.mocked(reloadPage).mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('saves and applies css without reload', async () => {
    render(() => <DashboardProvider><CustomStylePanel /><ConfirmDialog /></DashboardProvider>);

    const editor = await screen.findByLabelText('自定义 CSS');
    await fireEvent.input(editor, { target: { value: '.slx-panel { border-radius: 0; }' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    await vi.waitFor(() => expect(localStorage.getItem('sl-custom-css')).toContain('.slx-panel'));
    expect(document.getElementById('slx-custom-style')?.textContent).toContain('.slx-panel');
    expect(replaceLocation).not.toHaveBeenCalled();
  });

  it('resets to default style after confirmation and reloads', async () => {
    localStorage.setItem('sl-custom-css', '.slx-panel{}');
    localStorage.setItem('sl-dashboard-theme', 'dark');
    render(() => <DashboardProvider><CustomStylePanel /><ConfirmDialog /></DashboardProvider>);

    fireEvent.click(await screen.findByRole('button', { name: '重置默认风格' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认' }));

    await vi.waitFor(() => expect(localStorage.getItem('sl-custom-css')).toBeNull());
    expect(localStorage.getItem('sl-dashboard-theme')).toBeNull();
    // 刷新有 600ms 延迟，轮询等待
    await vi.waitFor(() => expect(reloadPage).toHaveBeenCalled(), { timeout: 2000 });
  });

  it('shows the enabled badge only when css is saved', async () => {
    localStorage.setItem('sl-custom-css', '.slx-panel{}');
    render(() => <DashboardProvider><CustomStylePanel /></DashboardProvider>);

    expect(await screen.findByText('已启用')).toBeTruthy();
  });
});
