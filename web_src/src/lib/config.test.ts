import { describe, expect, it } from 'vitest';
import { configValuesEqual, normalizeFieldValue } from './config';

describe('configuration normalization', () => {
  it('normalizes booleans, numbers, arrays and json', () => {
    expect(normalizeFieldValue({ key: 'a', type: 'boolean' }, 'true')).toBe(true);
    expect(normalizeFieldValue({ key: 'a', type: 'integer' }, '12')).toBe(12);
    expect(normalizeFieldValue({ key: 'a', type: 'array' }, 'a, b')).toEqual(['a', 'b']);
    expect(normalizeFieldValue({ key: 'a', type: 'json' }, '{"ok":true}')).toEqual({ ok: true });
  });

  it('compares normalized values', () => {
    expect(configValuesEqual({ key: 'a', type: 'integer' }, '2', 2)).toBe(true);
  });
});
