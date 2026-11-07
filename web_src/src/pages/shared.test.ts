import { describe, expect, it } from 'vitest';
import { detailText, intelligenceScore, jargonPendingTotal, reviewBacklog } from './shared';
import type { DashboardSnapshot } from '../types/dashboard';

describe('reviewBacklog', () => {
  it('sums paginated totals and removes style reviews mixed into persona updates', () => {
    const data = {
      persona_updates: { updates: [{ id: 1, review_source: 'traditional' }, { id: 2, review_source: 'style_learning' }], total: 6 },
      style_learning_reviews: { reviews: [{ id: 2 }], total: 2 },
      jargon_reviews: { jargon_list: [{ id: 9 }], total: 25 },
    } as DashboardSnapshot;
    // 人格首屏混入风格审查：6 - 2 = 4，避免与风格待审重复计数
    expect(reviewBacklog(data)).toEqual({ personaPending: 4, styleTotal: 2, jargonPending: 25, total: 31 });
  });

  it('keeps persona totals when no style reviews are mixed in', () => {
    const data = {
      persona_updates: { updates: [{ id: 1, review_source: 'traditional' }], total: 3 },
      style_learning_reviews: { reviews: [], total: 1 },
      jargon_reviews: { jargon_list: [], total: 0 },
    } as DashboardSnapshot;
    expect(reviewBacklog(data).total).toBe(4);
  });

  it('falls back to list lengths when totals are missing', () => {
    const data = { persona_updates: [{ id: 1 }, { id: 2 }], style_learning_reviews: [{ id: 3 }] } as unknown as DashboardSnapshot;
    expect(reviewBacklog(data)).toMatchObject({ personaPending: 2, styleTotal: 1, jargonPending: 0, total: 3 });
  });
});

describe('intelligenceScore', () => {
  it('normalizes ratios to a 0-100 score and counts dimensions', () => {
    expect(intelligenceScore({ intelligence: { overall_score: 0.455, dimensions: { a: 1, b: 2 } } } as DashboardSnapshot))
      .toEqual({ score: 45.5, dimensions: 2 });
    expect(intelligenceScore({ intelligence: { overall_score: 140 } } as DashboardSnapshot).score).toBe(100);
    expect(intelligenceScore({} as DashboardSnapshot)).toEqual({ score: 0, dimensions: 0 });
  });
});

describe('detailText', () => {
  it('summarizes detail objects instead of printing [object Object]', () => {
    expect(detailText({ cpu_percent: 3, nested: { a: 1 }, flag: null, extra: 'hidden' })).toBe('cpu_percent: 3 · nested: {"a":1} · flag: null');
    expect(detailText('ok')).toBe('ok');
    expect(detailText({})).toBe('--');
    expect(detailText(undefined)).toBe('--');
  });
});

describe('jargonPendingTotal', () => {
  it('reads the paginated envelope total instead of the truncated list length', () => {
    const data = {
      jargon_reviews: {
        jargon_list: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }],
        total: 7,
        page_size: 5,
      },
    } as DashboardSnapshot;
    // 全局待审请求 page_size=5，超过 5 条时列表长度会少算
    expect(jargonPendingTotal(data)).toBe(7);
  });

  it('returns 0 for an empty pending queue', () => {
    const data = {
      jargon_reviews: { jargon_list: [], total: 0, data: [] },
    } as DashboardSnapshot;
    expect(jargonPendingTotal(data)).toBe(0);
  });

  it('falls back to list length for legacy array snapshots', () => {
    const data = { jargon_reviews: [{ id: 1 }, { id: 2 }] } as unknown as DashboardSnapshot;
    expect(jargonPendingTotal(data)).toBe(2);
  });

  it('falls back to list length when the envelope has no total', () => {
    const data = {
      jargon_reviews: { data: [{ id: 1 }] },
    } as DashboardSnapshot;
    expect(jargonPendingTotal(data)).toBe(1);
  });

  it('returns 0 when the pending snapshot is missing', () => {
    expect(jargonPendingTotal({} as DashboardSnapshot)).toBe(0);
  });

  it('falls back to stats when the pending queue request failed', () => {
    // 待审请求失败时快照是空对象，不能当成“队列已清空”
    const data = {
      jargon_reviews: {},
      jargon_stats: { total_candidates: 4, confirmed_jargon: 1 },
    } as DashboardSnapshot;
    expect(jargonPendingTotal(data)).toBe(3);
  });
});
