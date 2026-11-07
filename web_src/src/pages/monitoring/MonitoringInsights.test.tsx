import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

vi.mock('../../components/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}));

// 运行监控 / AI 巡检：与内嵌插件页同口径的读数、行字段与巡检规则。

const json = (payload: unknown, status = 200) => new Response(
  JSON.stringify(payload),
  { status, headers: { 'Content-Type': 'application/json' } },
);

const installFetch = (override: (url: string) => Response | undefined = () => undefined) => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    const custom = override(url);
    if (custom) return custom;
    if (url.endsWith('/api/metrics')) {
      return json({
        filtered_messages: 0,
        llm_call_summary: { total_calls: 49, abnormal_provider_count: 1 },
        llm_call_breakdown: [
          { provider_type: 'filter', provider_label: 'FilterModel', total_calls: 40, avg_response_time_ms: 120.4, error_count: 1, is_abnormal: true },
          { provider_type: 'refine', provider_label: 'RefineModel', total_calls: 9, avg_response_time_ms: 300, error_count: 0, is_abnormal: false },
        ],
      });
    }
    if (url.includes('/api/monitoring/health')) {
      return json({ overall: 'healthy', checks: { cpu: { status: 'healthy', detail: { cpu_percent: 3 } } } });
    }
    if (url.includes('/api/intelligence_metrics')) return json({ overall_score: 45.5, dimensions: { a: 1, b: 2, c: 3 } });
    return json({});
  });
};

describe('monitoring page', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows the score stat, readable health details and provider rows', async () => {
    installFetch();
    window.location.hash = '#/monitoring';
    render(() => <App />);
    expect(await screen.findByText('已有 3 个维度参与评估。')).toBeInTheDocument();
    expect(screen.getByText('综合评分')).toBeInTheDocument();
    expect(screen.getByText('45.5')).toBeInTheDocument();
    expect(screen.getByText('检查核心能力、后台任务与模型调用的运行状态。')).toBeInTheDocument();
    // 健康明细按 key: value 摘要，不再输出 [object Object]
    expect(screen.getByText('cpu_percent: 3')).toBeInTheDocument();
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
    // 模型调用行读 provider_label / is_abnormal（与内嵌页同字段）
    expect(screen.getByText('FilterModel')).toBeInTheDocument();
    expect(screen.getByText('平均 120ms · 失败 1')).toBeInTheDocument();
    expect(screen.getByText('40').closest('.slx-badge')).toHaveClass('slx-badge-danger');
    expect(screen.getByText('9').closest('.slx-badge')).toHaveClass('slx-badge-default');
    expect(screen.getByText('49 次调用')).toBeInTheDocument();
    expect(screen.getByText('当前没有函数追踪样本；可在配置中开启 trace。')).toBeInTheDocument();
  });

  it('shows empty states when no checks or provider calls exist', async () => {
    installFetch((url) => {
      if (url.includes('/api/monitoring/health')) return json({ overall: 'healthy', checks: {} });
      if (url.includes('/api/intelligence_metrics')) return json({ overall_score: 0, dimensions: {} });
      if (url.endsWith('/api/metrics')) return json({ llm_call_breakdown: [], llm_call_summary: { total_calls: 0 } });
      return undefined;
    });
    window.location.hash = '#/monitoring';
    render(() => <App />);
    expect(await screen.findByText('暂无健康检查数据')).toBeInTheDocument();
    expect(screen.getByText('暂无模型调用统计')).toBeInTheDocument();
    expect(screen.getByText('智能指标服务暂未产生维度数据。')).toBeInTheDocument();
    expect(screen.getByText('0 次调用')).toBeInTheDocument();
  });
});

describe('insights page', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('includes the ported rules and copies a summary', async () => {
    installFetch((url) => {
      if (url.includes('/api/monitoring/health')) return json({ overall: 'healthy', checks: {}, runtime: { database_degraded: true, database_start_error: null } });
      if (url.includes('/api/integrations/status')) return json({ delegation: { memory_delegated: true, reply_delegated: false }, dashboards: [] });
      if (url.includes('/api/metrics/trends')) return json({ error: '趋势读取失败' }, 500);
      if (url.includes('/api/hub/v1/status')) return json({ success: false, message: 'loopback only' }, 403);
      return undefined;
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    window.location.hash = '#/insights';
    render(() => <App />);
    expect(await screen.findByText('数据库处于降级状态')).toBeInTheDocument();
    expect(screen.getByText('数据库服务未完整启动。')).toBeInTheDocument();
    expect(screen.getByText('智能评分偏低')).toBeInTheDocument();
    expect(await screen.findByText('伴随插件委托已启用')).toBeInTheDocument();
    expect(screen.getByText('记忆委托: 是，回复委托: 否。')).toBeInTheDocument();
    expect(screen.getByText('模块 trends 读取失败')).toBeInTheDocument();
    // Hub API 未启用鉴权时仅允许本机调用，失败属预期，不作为巡检告警
    expect(screen.queryByText('模块 hub_status 读取失败')).not.toBeInTheDocument();
    expect(screen.getAllByText('高').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('中').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('提示').length).toBeGreaterThanOrEqual(1);

    await fireEvent.click(screen.getByRole('button', { name: '复制摘要' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain('- 数据库处于降级状态: 数据库服务未完整启动。');
    expect(writeText.mock.calls[0][0]).toContain('- 模块 trends 读取失败: 趋势读取失败');
    expect(await screen.findByText('巡检摘要已复制')).toBeInTheDocument();
  });
});
