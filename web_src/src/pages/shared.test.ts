import { describe, expect, it } from 'vitest';
import { jargonPendingTotal } from './shared';
import type { DashboardSnapshot } from '../types/dashboard';

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
});
