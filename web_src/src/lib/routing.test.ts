import { describe, expect, it } from 'vitest';
import { DASHBOARD_PAGES, pageHref, parseHash } from './routing';

describe('hash routing', () => {
  it('supports all dashboard pages and falls back safely', () => {
    for (const page of DASHBOARD_PAGES) expect(parseHash(pageHref(page))).toBe(page);
    expect(parseHash('#/missing')).toBe('home');
  });
});
