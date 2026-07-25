import type { PageId } from '../types/dashboard';

export const DASHBOARD_PAGES: PageId[] = [
  'home', 'overview', 'insights', 'monitoring', 'reviews', 'jargon-learning',
  'expression-learning', 'persona-learning', 'content', 'reply-strategy',
  'shadow-mode', 'graphs', 'integrations', 'settings',
];

export function parseHash(hash = window.location.hash): PageId {
  const candidate = hash.replace(/^#\/?/, '').split(/[?#]/)[0] as PageId;
  return DASHBOARD_PAGES.includes(candidate) ? candidate : 'home';
}

export function pageHref(page: PageId): string {
  return `#/${page}`;
}

function isLocalNavigationHost(hostname: string): boolean {
  const host = hostname.trim().replace(/^\[(.*)\]$/, '$1').toLowerCase();
  if (!host) return true;
  return host === 'localhost'
    || host === '0.0.0.0'
    || host === '::'
    || host === '::1'
    || host === '0:0:0:0:0:0:0:0'
    || host === '0:0:0:0:0:0:0:1'
    || /^127(?:\.\d{1,3}){3}$/.test(host);
}

function hostForUrl(hostname: string): string {
  const host = hostname.trim().replace(/^\[(.*)\]$/, '$1');
  return host.includes(':') ? `[${host}]` : host;
}

/** Resolve companion WebUI loopback URLs from the browser that opened this dashboard. */
export function resolveHostUrl(value: string, browserHref = window.location.href): string {
  const raw = value.trim();
  if (!raw || raw === '#' || raw.startsWith('#')) return raw;

  let target: URL;
  let browser: URL;
  try {
    target = new URL(raw, browserHref);
    browser = new URL(browserHref);
  } catch {
    return raw;
  }

  if (!/^https?:$/.test(target.protocol) || !isLocalNavigationHost(target.hostname)) {
    return raw;
  }

  const replacementHost = hostForUrl(browser.hostname);
  if (!replacementHost) return raw;
  target.host = target.port ? `${replacementHost}:${target.port}` : replacementHost;
  return target.href;
}
