import { describe, expect, it } from 'vitest';
import { buildJargonListParams } from './JargonLearningPage';

describe('buildJargonListParams', () => {
  it('maps search to the backend keyword parameter', () => {
    const params = buildJargonListParams({
      page: 2,
      pageSize: 10,
      filter: 'all',
      search: '  赛博黑话  ',
    });

    expect(params.get('page')).toBe('2');
    expect(params.get('page_size')).toBe('10');
    expect(params.get('keyword')).toBe('赛博黑话');
    expect(params.has('search')).toBe(false);
  });

  it('maps status filters to supported backend parameters', () => {
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'pending', search: '' }).get('pending')).toBe('true');
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'confirmed', search: '' }).get('confirmed')).toBe('true');
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'unconfirmed', search: '' }).get('confirmed')).toBe('false');
  });

  it('maps the scope filter to the backend filter parameter', () => {
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'all', search: '', scope: 'global' }).get('filter')).toBe('global');
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'all', search: '', scope: 'local' }).get('filter')).toBe('local');
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'all', search: '', scope: 'all' }).has('filter')).toBe(false);
    expect(buildJargonListParams({ page: 1, pageSize: 10, filter: 'all', search: '' }).has('filter')).toBe(false);
  });
});
