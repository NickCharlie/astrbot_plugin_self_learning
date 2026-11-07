import { describe, expect, it } from 'vitest';
import type { DashboardSnapshot } from '../../types/dashboard';
import { buildInsights, insightLevel } from './insights';

// AI 巡检规则集：与内嵌插件页 app.js buildInsights 同一组规则、顺序与文案。

describe('buildInsights', () => {
  it('reports nothing-to-handle on an empty snapshot', () => {
    expect(buildInsights({} as DashboardSnapshot)).toEqual([
      { title: '暂未发现需要立即处理的问题', detail: '当前快照没有明显积压或健康告警。', tone: 'success', page: 'overview', value: 0 },
    ]);
  });

  it('emits every rule in order with the shared copy', () => {
    const data = {
      health: {
        overall: 'degraded',
        checks: { cpu: { status: 'healthy' }, cache: { status: 'degraded' }, llm: { status: 'unhealthy' } },
        runtime: { database_degraded: true, database_start_error: 'sqlite locked' },
      },
      persona_updates: { updates: [{ id: 1, review_source: 'style_learning' }], total: 6 },
      style_learning_reviews: { reviews: [], total: 2 },
      jargon_reviews: { jargon_list: [], total: 25 },
      metrics: { filtered_messages: 2061 },
      intelligence: { overall_score: 45.5, dimensions: { a: 1 } },
      load_errors: { trends: '请求失败（HTTP 500）' },
    } as DashboardSnapshot;
    const rows = buildInsights(data, { delegation: { memory_delegated: true, reply_delegated: false } });
    expect(rows.map((row) => [row.title, row.detail, row.tone, row.page])).toEqual([
      ['数据库处于降级状态', 'sqlite locked', 'danger', 'monitoring'],
      ['审查队列存在积压', '当前约 31 条记录等待处理。', 'danger', 'reviews'],
      ['过滤链路持续工作', '2,061 条消息因质量或规则未进入学习。', 'default', 'monitoring'],
      ['健康检查发现异常', '2 项检查未处于健康状态。', 'danger', 'monitoring'],
      ['智能评分偏低', '综合评分 45.5，建议查看表达样本和学习批次。', 'warning', 'monitoring'],
      ['伴随插件委托已启用', '记忆委托: 是，回复委托: 否。', 'default', 'integrations'],
      ['模块 trends 读取失败', '请求失败（HTTP 500）', 'warning', 'monitoring'],
    ]);
  });

  it('uses the warning tone for a small backlog and the default degraded-database copy', () => {
    const rows = buildInsights({
      health: { runtime: { database_degraded: true } },
      persona_updates: { updates: [], total: 3 },
    } as DashboardSnapshot);
    expect(rows[0]).toMatchObject({ title: '数据库处于降级状态', detail: '数据库服务未完整启动。' });
    expect(rows[1]).toMatchObject({ title: '审查队列存在积压', tone: 'warning', value: 3 });
  });

  it('skips the score rule for a missing or healthy score', () => {
    expect(buildInsights({ intelligence: { overall_score: 0 } } as DashboardSnapshot)[0].title).toBe('暂未发现需要立即处理的问题');
    expect(buildInsights({ intelligence: { overall_score: 72 } } as DashboardSnapshot)[0].title).toBe('暂未发现需要立即处理的问题');
  });
});

describe('insightLevel', () => {
  it('maps tones to the 高 / 中 / 提示 badges', () => {
    expect(insightLevel('danger')).toBe('高');
    expect(insightLevel('warning')).toBe('中');
    expect(insightLevel('default')).toBe('提示');
    expect(insightLevel('success')).toBe('提示');
  });
});
