import type { PageId } from '../types/dashboard';

export const DASHBOARD_PAGES: PageId[] = [
  'home', 'overview', 'insights', 'monitoring', 'reviews', 'jargon-learning',
  'expression-learning', 'persona-learning', 'content', 'reply-strategy',
  'graphs', 'integrations', 'settings',
];

export function parseHash(hash = window.location.hash): PageId {
  const candidate = hash.replace(/^#\/?/, '').split(/[?#]/)[0] as PageId;
  return DASHBOARD_PAGES.includes(candidate) ? candidate : 'home';
}

export function pageHref(page: PageId): string {
  return `#/${page}`;
}
