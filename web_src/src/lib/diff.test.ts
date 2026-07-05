import { describe, expect, it } from 'vitest';
import { buildLineDiff } from './diff';

describe('buildLineDiff', () => {
  it('marks added, removed and unchanged lines', () => {
    const result = buildLineDiff('one\ntwo', 'one\nthree');
    expect(result).toContainEqual({ kind: 'same', text: 'one' });
    expect(result).toContainEqual({ kind: 'remove', text: 'two' });
    expect(result).toContainEqual({ kind: 'add', text: 'three' });
  });
});
