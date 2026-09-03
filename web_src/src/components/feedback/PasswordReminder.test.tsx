import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PasswordReminderBanner } from './PasswordReminder';

const jsonOk = (payload: unknown) => new Response(JSON.stringify(payload), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
});

describe('PasswordReminderBanner', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows the reminder when password auth is disabled', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonOk({ password_enabled: false }));

    render(() => <PasswordReminderBanner />);

    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy());
  });

  it('stays hidden when password auth is enabled', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonOk({ password_enabled: true }));

    render(() => <PasswordReminderBanner />);

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('does not query the backend after dismissal', async () => {
    localStorage.setItem('selflearning.password-reminder.dismissed', '1');
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    render(() => <PasswordReminderBanner />);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('persists dismissal on click', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonOk({ password_enabled: false }));

    render(() => <PasswordReminderBanner />);
    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '知道了' }));

    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(localStorage.getItem('selflearning.password-reminder.dismissed')).toBe('1');
  });
});
