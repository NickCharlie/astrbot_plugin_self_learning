export type DiffLine = { kind: 'add' | 'remove' | 'same'; text: string };

export function buildLineDiff(beforeValue: unknown, afterValue: unknown): DiffLine[] {
  const before = String(beforeValue ?? '').split(/\r?\n/);
  const after = String(afterValue ?? '').split(/\r?\n/);
  const rows = before.length + 1;
  const cols = after.length + 1;
  const table = Array.from({ length: rows }, () => Array<number>(cols).fill(0));
  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = after.length - 1; j >= 0; j -= 1) {
      table[i][j] = before[i] === after[j]
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < before.length || j < after.length) {
    if (i < before.length && j < after.length && before[i] === after[j]) {
      result.push({ kind: 'same', text: before[i] }); i += 1; j += 1;
    } else if (j < after.length && (i >= before.length || table[i][j + 1] >= table[i + 1][j])) {
      result.push({ kind: 'add', text: after[j] }); j += 1;
    } else {
      result.push({ kind: 'remove', text: before[i] }); i += 1;
    }
  }
  return result;
}
