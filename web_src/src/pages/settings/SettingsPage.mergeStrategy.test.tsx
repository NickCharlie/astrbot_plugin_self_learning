import { fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardProvider } from '../../stores/dashboard';
import { SettingsPage } from '../../pages/settings/SettingsPage';

const mergeStrategyOptions = [
  { value: 'replace', label: '替换' },
  { value: 'append', label: '追加' },
  { value: 'prepend', label: '前置' },
  { value: 'smart', label: '智能' },
];

const buildSchema = (initialValue: string) => ({
  config: { persona_merge_strategy: initialValue, enable_persona_evolution: true },
  groups: [
    {
      key: 'Persona_Evolution_Settings',
      title: '人格演化',
      hint: '控制人格合并、自动应用和更新备份',
      fields: [
        {
          key: 'persona_merge_strategy',
          label: '人格合并策略',
          hint: '控制人格更新时的合并方式',
          type: 'string',
          widget: 'text',
          default: 'smart',
          value: initialValue,
          editable: true,
          options: mergeStrategyOptions,
        },
        {
          key: 'enable_persona_evolution',
          label: '启用人格演化跟踪',
          type: 'bool',
          widget: 'toggle',
          value: true,
          editable: true,
        },
      ],
    },
  ],
  warnings: [],
  provider_options: [],
  provider_options_by_type: { chat_completion: [], embedding: [], rerank: [] },
});

const buildConfig = (initialValue: string) => ({ persona_merge_strategy: initialValue, enable_persona_evolution: true });

const installFetchMock = (initialValue: string) => {
  const posts: Array<{ url: string; body: unknown }> = [];
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    if (method === 'POST') {
      posts.push({ url, body: JSON.parse(String(init?.body || '{}')) });
      return new Response(JSON.stringify({ message: 'ok', new_config: posts.at(-1)!.body }), { status: 200 });
    }
    if (url.includes('/api/config/schema')) return new Response(JSON.stringify(buildSchema(initialValue)), { status: 200 });
    if (url.includes('/api/config')) return new Response(JSON.stringify(buildConfig(initialValue)), { status: 200 });
    if (url.includes('/api/integrations/status')) return new Response(JSON.stringify({}), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal('fetch', mock);
  return posts;
};

describe('settings persona merge strategy (issue #243)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the stored merge strategy even when it is not the first option', async () => {
    installFetchMock('smart');
    const view = render(() => (
      <DashboardProvider>
        <SettingsPage />
      </DashboardProvider>
    ));

    const select = await waitFor(() => {
      const element = Array.from(document.querySelectorAll('select')).find((item) =>
        Array.from(item.options).some((option) => option.value === 'smart'),
      );
      expect(element).toBeTruthy();
      return element as HTMLSelectElement;
    });
    await waitFor(() => expect(select.value).toBe('smart'));

    view.unmount();
  });

  it('enables save and submits the changed merge strategy', async () => {
    const posts = installFetchMock('replace');
    const view = render(() => (
      <DashboardProvider>
        <SettingsPage />
      </DashboardProvider>
    ));

    const select = await waitFor(() => {
      const element = Array.from(document.querySelectorAll('select')).find((item) =>
        Array.from(item.options).some((option) => option.value === 'smart'),
      );
      expect(element).toBeTruthy();
      return element as HTMLSelectElement;
    });
    await waitFor(() => expect(select.value).toBe('replace'));

    const saveButton = screen.getByRole('button', { name: /手动保存设置/ });
    expect(saveButton).toBeDisabled();

    await fireEvent.change(select, { target: { value: 'smart' } });

    await waitFor(() => expect(screen.getByRole('button', { name: /手动保存设置/ })).not.toBeDisabled());

    await fireEvent.click(screen.getByRole('button', { name: /手动保存设置/ }));

    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/config'))).toBe(true));
    const configPost = posts.find((post) => post.url.includes('/api/config'))!;
    expect(configPost.body).toMatchObject({ persona_merge_strategy: 'smart' });

    await waitFor(() => {
      const current = Array.from(document.querySelectorAll('select')).find((item) =>
        Array.from(item.options).some((option) => option.value === 'smart'),
      ) as HTMLSelectElement;
      expect(current.value).toBe('smart');
    });

    view.unmount();
  });
});
