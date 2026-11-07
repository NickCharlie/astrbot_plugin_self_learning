import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 双端取并集：委托徽标 / dev_api.mode / 打开面板回退内嵌路由 / 融合设置面板 /
// 世界书历史（名称 + 条目数 + 状态）此前只有内嵌页有，移植到独立版后回归锁定。

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

let previewPayload: Record<string, unknown> | null = null;

const installFetch = () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (url.includes('/api/integrations/worldbook/preview')) {
      previewPayload = JSON.parse(String(init?.body ?? '{}'));
      return json({ success: true, data: { counts: { entries: 2, enabled_entries: 1, disabled_entries: 1, keywords: 3 } } });
    }
    if (url.includes('/api/integrations/worldbook/imports')) {
      return json({
        success: true,
        data: {
          imports: [
            { import_id: 'imp1', worldbook_name: '测试世界书', entries: 3, status: 'approved', imported_at: '2026-11-07T10:00:00' },
            { import_id: 'imp2', worldbook_name: null, entries: 1, status: 'pending', imported_at: '2026-11-06T10:00:00' },
          ],
        },
      });
    }
    if (url.includes('/api/integrations/status')) {
      return json({
        warnings: ['LightRAG 与 LivingMemory 同时启用，成本较高。'],
        settings: { delegate_memory_to_livingmemory: true, group_chat_plus_plugin_name: null },
        dashboards: [
          {
            id: 'self_learning', title: 'Self Learning', role: '学习、审查与上下文注入', active: true,
            status: { healthy: true, message: '本插件监控板运行中' },
            dashboard: { available: true, route: '#/home', label: '本插件监控板' },
          },
          {
            id: 'livingmemory', title: 'LivingMemory', role: '长期记忆与图谱', active: true, delegated: true,
            dev_api: { mode: 'self_learning_graph_store_adapter' },
            status: { healthy: null, state: 'unknown' },
            dashboard: { available: true, external_url: '', route: '#/graphs' },
          },
          {
            id: 'group_chat_plus', title: 'Group Chat Plus', role: '回复决策与生成', active: false, delegated: false,
            status: { healthy: null, state: 'not_installed' },
            dashboard: { available: false },
          },
        ],
      });
    }
    return json({});
  });
};

describe('integrations union parity', () => {
  beforeEach(() => {
    localStorage.clear();
    previewPayload = null;
    installFetch();
    window.location.hash = '#/integrations';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('renders status badges, a separate delegation badge and dev api mode on cards', async () => {
    render(() => <App />);

    const panel = (await screen.findByText('伴随插件状态')).closest('section')!;
    expect(await within(panel).findByText('正常')).toBeInTheDocument();
    expect(within(panel).getByText('未知')).toBeInTheDocument();
    expect(within(panel).getByText('未安装')).toBeInTheDocument();
    // 委托徽标独立展示：LM 已委托，GCP 未委托，self_learning 无委托标记
    expect(within(panel).getByText('已委托')).toBeInTheDocument();
    expect(within(panel).getByText('未委托')).toBeInTheDocument();
    // 内嵌页既有信息移植：dev_api.mode
    expect(within(panel).getByText('self_learning_graph_store_adapter')).toBeInTheDocument();
    // 统一为固定「打开面板」按钮（不再用后端 label 作为按钮文本）
    expect(within(panel).getAllByRole('button', { name: '打开面板' })).toHaveLength(3);
  });

  it('falls back to the internal route when a card has no external url', async () => {
    render(() => <App />);

    const panel = (await screen.findByText('伴随插件状态')).closest('section')!;
    const buttons = await within(panel).findAllByRole('button', { name: '打开面板' });
    // self_learning 卡片无 external_url：回退到内嵌 #/home 路由
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(window.location.hash).toBe('#/home'));
  });

  it('shows the ported delegation settings panel with cost warnings', async () => {
    render(() => <App />);

    const panel = (await screen.findByText('融合设置')).closest('section')!;
    expect(await within(panel).findByText('成本提醒')).toBeInTheDocument();
    expect(within(panel).getByText('LightRAG 与 LivingMemory 同时启用，成本较高。')).toBeInTheDocument();
    expect(within(panel).getByText('delegate_memory_to_livingmemory')).toBeInTheDocument();
    expect(within(panel).getByText('开启')).toBeInTheDocument();
    expect(within(panel).getByText('未设置')).toBeInTheDocument();
  });

  it('lists worldbook history with name, entry count and status, and summarizes results', async () => {
    render(() => <App />);

    const panel = (await screen.findByText('世界书导入')).closest('section')!;
    const summary = await within(panel).findByText(/最近导入记录（2）/);
    fireEvent.click(summary);
    expect(await within(panel).findByText('测试世界书')).toBeInTheDocument();
    expect(within(panel).getByText('3')).toBeInTheDocument();
    expect(within(panel).getByText('approved')).toBeInTheDocument();
    // worldbook_name 缺失时回退 import_id（与内嵌页一致）
    expect(within(panel).getByText('imp2')).toBeInTheDocument();

    const textarea = within(panel).getByLabelText('世界书 JSON');
    fireEvent.input(textarea, { target: { value: '{"entries": {}}' } });
    fireEvent.click(within(panel).getByRole('button', { name: '预览' }));
    // 人类可读摘要行 + 原始 JSON
    expect(await within(panel).findByText(/预览: 条目 2（启用 1 \/ 禁用 1）· 关键词 3/)).toBeInTheDocument();
    expect(await within(panel).findByText(/"counts"/)).toBeInTheDocument();
    expect(previewPayload?.payload).toEqual({ entries: {} });
  });
});
