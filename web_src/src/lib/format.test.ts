import { describe, expect, it } from 'vitest';
import { clamp, formatCount, formatPercent, formatTime, getPath, safeNumber } from './format';

describe('format helpers', () => {
  it('normalizes numeric values', () => {
    expect(safeNumber('12.5')).toBe(12.5);
    expect(safeNumber('nope', 3)).toBe(3);
    expect(clamp(120)).toBe(100);
    expect(formatCount(1234)).toContain('1');
    expect(formatPercent(.5, 1)).toBe('0.5%');
  });

  it('formats timestamps and resolves nested paths', () => {
    expect(formatTime(null)).toBe('--');
    expect(formatTime(1_700_000_000)).not.toBe('--');
    expect(getPath({ a: { b: 7 } }, 'a.b')).toBe(7);
  });
});
