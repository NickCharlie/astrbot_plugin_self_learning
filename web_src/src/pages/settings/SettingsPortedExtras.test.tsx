import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 内嵌页既有信息移植回归：成本提醒列表、「 · 重启后生效」提示、pip 输出框。

const schema = {
  groups: [
    {
      key: 'Basic_Settings',
      title: '基础设置',
      hint: '基础行为',
      fields: [
        { key: 'restart_me', label: '需要重启的项', description: '开关后需重启', type: 'bool', widget: 'toggle', value: false, editable: true, restart_required: true },
        { key: 'plain_field', label: '普通字段', type: 'string', widget: 'text', value: 'abc', editable: true },
      ],
    },
  ],
  warnings: ['LightRAG 与 LivingMemory 同时启用，成本较高。'],
  provider_options: [],
};

const installFetch = (installResponse: () => Response) => {
  const posts: Array<{ url: string; body: unknown }> = [];
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    if (method === 'POST') {
      posts.push({ url, body: JSON.parse(String(init?.body || '{}')) });
      return installResponse();
    }
    if (url.includes('/api/config/schema')) return new Response(JSON.stringify(schema), { status: 200 });
    if (url.includes('/api/config')) return new Response(JSON.stringify({ restart_me: false, plain_field: 'abc' }), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal('fetch', mock);
  return posts;
};

describe('settings ported extras', () => {
  beforeEach(() => {
    localStorage.clear();
    window.location.hash = '#/settings';
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('renders cost warnings and restart-required hint suffixes', async () => {
    installFetch(() => new Response('{}', { status: 200 }));
    render(() => <App />);

    expect(await screen.findByText('成本提醒')).toBeInTheDocument();
    expect(screen.getByText('LightRAG 与 LivingMemory 同时启用，成本较高。')).toBeInTheDocument();
    const toggleLabel = await screen.findByText('需要重启的项');
    expect(toggleLabel.parentElement).toHaveTextContent(' · 重启后生效');
    const plainLabel = screen.getByText('普通字段');
    expect(plainLabel.parentElement).not.toHaveTextContent('重启后生效');
  });

  it('shows pip output after an installed dependency tier', async () => {
    const posts = installFetch(() => new Response(JSON.stringify({ message: '基础安装完成', output: 'Successfully installed aiohttp' }), { status: 200 }));
    render(() => <App />);

    fireEvent.click(await screen.findByRole('button', { name: /基础能力依赖/ }));
    fireEvent.click(await screen.findByRole('button', { name: '确认' }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({ manual_confirmed: true, tier: 'basic', pip_mirror: 'default' });
    expect(await screen.findByText('Successfully installed aiohttp')).toBeInTheDocument();
    expect(screen.getByText('依赖安装任务已完成')).toBeInTheDocument();
  });
});
