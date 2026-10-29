import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 后端 /api/data/clear/* 与 /api/bug_report/* 此前没有 WebUI 入口，这里回归验证补上的面板。

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

let clearCalls: string[] = [];
let bugPayload: Record<string, unknown> | null = null;

const installFetch = () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method === 'DELETE' && url.includes('/api/data/clear/')) {
      clearCalls.push(url.split('/api/data/clear/')[1]);
      return json({ success: true, message: '已清除 5 条消息数据', deleted: 5 });
    }
    if (url.includes('/api/data/statistics')) {
      return json({
        success: true,
        data: {
          messages: 12, persona_reviews: 3, style_learning: 4, jargon: 5,
          learning_history: 6, memory: 7, knowledge_graph: 8, runtime_state: 9,
        },
      });
    }
    if (method === 'POST' && url.includes('/api/bug_report')) {
      bugPayload = JSON.parse(String(init?.body ?? '{}'));
      return json({ success: true, message: 'Bug报告提交成功' });
    }
    if (url.includes('/api/bug_report/config')) {
      return json({
        enabled: true,
        defaultBuild: 'v4.4.3',
        severityOptions: [{ value: 3, label: '3 - 一般' }],
        priorityOptions: [{ value: 3, label: '3 - 中' }],
        typeOptions: [{ value: 'codeerror', label: '代码错误' }],
        logPreview: {},
      });
    }
    if (url.includes('/api/bug_report/history')) return json({ history: [] });
    return json({});
  });
};

describe('settings data management and bug report panels', () => {
  beforeEach(() => {
    localStorage.clear();
    clearCalls = [];
    bugPayload = null;
    installFetch();
    window.location.hash = '#/settings';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows data statistics and clears a module after confirmation', async () => {
    render(() => <App />);

    const title = await screen.findByText('数据管理');
    const panel = title.closest('section');
    expect(panel).not.toBeNull();
    expect(await within(panel!).findByText('12')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '清空消息数据' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认清空' }));

    await waitFor(() => expect(clearCalls).toEqual(['messages']));
  });

  it('submits a bug report with the required fields', async () => {
    render(() => <App />);

    const title = await screen.findByLabelText('Bug 标题');
    // 等待配置加载并回填默认影响版本，避免提交时 build 仍为空
    const buildInput = await screen.findByLabelText('影响版本');
    await waitFor(() => expect(buildInput).toHaveValue('v4.4.3'));
    // 下拉选项由 config 异步替换后，受控值不能回退到第一项
    expect(screen.getByLabelText('严重程度')).toHaveValue('3');
    expect(screen.getByLabelText('优先级')).toHaveValue('3');
    fireEvent.input(title, { target: { value: '无法打开审核详情' } });
    const steps = screen.getByLabelText('重现步骤');
    fireEvent.input(steps, { target: { value: '1. 打开 WebUI' } });
    fireEvent.click(screen.getByRole('button', { name: '提交 Bug 报告' }));

    await waitFor(() => expect(bugPayload?.title).toBe('无法打开审核详情'));
    expect(bugPayload?.steps).toBe('1. 打开 WebUI');
    expect(bugPayload?.severity).toBe(3);
    expect(bugPayload?.build).toBe('v4.4.3');
  });
});
