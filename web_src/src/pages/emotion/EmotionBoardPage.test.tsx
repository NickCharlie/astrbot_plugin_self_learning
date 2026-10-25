import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';
import { emotionListTotal } from './EmotionBoardPage';

// jsdom 无 canvas，图表组件与 App 冒烟测试保持一致的 mock 策略
vi.mock('../../components/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}));

// 情绪中枢板块：面板数据映射、遗忘阶段徽标与治理操作调用。

const json = (payload: Record<string, unknown>) => new Response(
  JSON.stringify({ success: true, ...payload }),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

const boardPayload = {
  available: true,
  moods: {
    active: [
      { group_id: 'g1', mood_type: 'happy', intensity: 0.8, description: '今天心情不错', timestamp: 1792800000, start_time: 1792800000 },
    ],
    history: [],
  },
  affection: {
    groups: [{ group_id: 'g1', total_users: 3, average: 44, high: 1, low: 0 }],
    leaderboard: [{ user_id: 'u-top', group_id: 'g1', level: 88 }],
    bottom: [{ user_id: 'u-low', group_id: 'g1', level: -35 }],
    overall: { total_users: 3, average: 44 },
  },
  emotion_profiles: { total: 2, dominant_distribution: [{ emotion: 'joy', count: 2 }] },
  gate: {
    daily: [{ stat_date: '2026-10-25', accepted: 8, skipped: 2, avg_score: 0.71, accept_rate: 0.8 }],
    telemetry: {
      enabled: true,
      threshold: 0.3,
      weights: { affection: 0.35, sentiment: 0.25, mood: 0.2, stability: 0.2 },
      recent: [
        { timestamp: 1792800100, group_id: 'g1', score: 0.9, decision: true },
        { timestamp: 1792800200, group_id: 'g1', score: 0.1, decision: false },
      ],
      counters: { accepted: 8, skipped: 2 },
      recent_factor_avg: { affection: 0.7, sentiment: 0.6, mood: 0.8, stability: 0.5 },
    },
  },
  forgetting: {
    enabled: true,
    running: true,
    last_run_at: 1792700000,
    config: { cycle_days: 7, grace_days: 14, protect_global_jargon: true, negative_fast_track: true, high_value_weight: 3.0 },
    stage_labels: { '0': '新鲜', '1': '遗忘观察一期', '2': '遗忘观察二期', '3': '待删除' },
    distribution: {
      expression: { '0': 5, '1': 1, '2': 1, '3': 0 },
      jargon: { '0': 8, '1': 0, '2': 0, '3': 1 },
    },
    candidates: {
      expression: [
        { id: 31, kind: 'expression', group_id: 'g1', title: '绝绝子', detail: '', stage: 2, last_used: 1792000000, created: 1791000000 },
      ],
      jargon: [
        { id: 41, kind: 'jargon', group_id: 'g1', title: 'yyds', detail: '永远的神', stage: 3, last_used: 1791000000, created: 1790000000 },
      ],
    },
    last_report: null,
  },
};

const trendsPayload = {
  days: 14,
  affection_delta: [{ date: '2026-10-24', delta: 6 }, { date: '2026-10-25', delta: -2 }],
  mood_changes: [{ date: '2026-10-25', count: 2 }],
  gate: boardPayload.gate.daily,
};

describe('emotion board page', () => {
  const state = { actions: [] as Array<Record<string, unknown>> };

  const installFetch = () => {
    state.actions = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      if (url.includes('/api/emotion/board')) return json({ data: boardPayload });
      if (url.includes('/api/emotion/trends')) return json({ data: trendsPayload });
      if (url.includes('/api/emotion/action')) {
        state.actions.push(JSON.parse(String(init?.body ?? '{}')));
        return json({ data: { success: true, message: '已标记为「遗忘观察二期」（marked_dislike）' } });
      }
      // store 初始化与刷新涉及的其他接口一律返回空成功
      return json({ data: {} });
    });
  };

  beforeEach(() => {
    window.location.hash = '#/emotion';
    installFetch();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.location.hash = '';
  });

  it('渲染心情、好感度、闸门与遗忘候选', async () => {
    render(() => <App />);

    await waitFor(() => expect(screen.getByRole('heading', { name: '情绪中枢' })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('开心')).toBeInTheDocument());
    // 平均好感度 44 出现在统计卡与群组概览中
    await waitFor(() => expect(screen.getAllByText('44').length).toBeGreaterThan(0));
    // 闸门累计放行/拦截
    expect(screen.getByText('累计放行')).toBeInTheDocument();
    expect(screen.getByText('累计拦截')).toBeInTheDocument();
    // 遗忘候选两条：表达（二期）与黑话（待删除）；阶段文案同时出现在分布芯片与徽标
    await waitFor(() => expect(screen.getByText('yyds')).toBeInTheDocument());
    expect(screen.getByText('绝绝子')).toBeInTheDocument();
    expect(screen.getAllByText('待删除').length).toBeGreaterThan(0);
    expect(screen.getAllByText('遗忘观察二期').length).toBeGreaterThan(0);
  });

  it('标记反感调用情绪板块治理动作', async () => {
    render(() => <App />);
    await waitFor(() => expect(screen.getByText('yyds')).toBeInTheDocument());

    const dislikeButtons = await screen.findAllByText('标记反感');
    fireEvent.click(dislikeButtons[0]);
    await waitFor(() => expect(state.actions.length).toBe(1));
    expect(state.actions[0].action).toBe('mark_dislike');
    expect(['expression', 'jargon']).toContain(state.actions[0].kind);
  });

  it('emotionListTotal 汇总两类候选', () => {
    expect(emotionListTotal(boardPayload.forgetting)).toBe(2);
    expect(emotionListTotal(null)).toBe(0);
    expect(emotionListTotal({ candidates: { expression: [{}, {}], jargon: [{}] } as never })).toBe(3);
  });
});
