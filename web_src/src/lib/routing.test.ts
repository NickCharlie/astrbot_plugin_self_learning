import { describe, expect, it } from 'vitest';
import { DASHBOARD_PAGES, pageHref, parseHash, resolveHostUrl } from './routing';

describe('hash routing', () => {
  it('supports all dashboard pages and falls back safely', () => {
    for (const page of DASHBOARD_PAGES) expect(parseHash(pageHref(page))).toBe(page);
    expect(parseHash('#/missing')).toBe('home');
  });
});

describe('companion dashboard URL resolution', () => {
  it('uses the current browser host for loopback and wildcard server addresses', () => {
    const browser = 'http://203.0.113.20:7833/#/reply-strategy';
    expect(resolveHostUrl('http://127.0.0.1:1451/panel?embed=1', browser))
      .toBe('http://203.0.113.20:1451/panel?embed=1');
    expect(resolveHostUrl('http://0.0.0.0:1451/panel', browser))
      .toBe('http://203.0.113.20:1451/panel');
    expect(resolveHostUrl('http://[::1]:1451/panel', browser))
      .toBe('http://203.0.113.20:1451/panel');
  });

  it('supports a remote IPv6 browser host', () => {
    expect(resolveHostUrl(
      'http://localhost:1451/panel?embed=1',
      'http://[2001:db8::42]:7833/#/reply-strategy',
    )).toBe('http://[2001:db8::42]:1451/panel?embed=1');
  });

  it('preserves explicit remote hosts and non-http links', () => {
    const browser = 'http://203.0.113.20:7833/';
    expect(resolveHostUrl('https://panel.example.com/panel', browser))
      .toBe('https://panel.example.com/panel');
    expect(resolveHostUrl('#/integrations', browser)).toBe('#/integrations');
  });
});
