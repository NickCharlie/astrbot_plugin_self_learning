export const safeNumber = (value: unknown, fallback = 0): number => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

export const clamp = (value: unknown, min = 0, max = 100): number =>
  Math.max(min, Math.min(max, safeNumber(value)));

const countFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 });

export const formatCount = (value: unknown): string =>
  countFormatter.format(Math.round(safeNumber(value)));

export const formatPercent = (value: unknown, digits = 0): string =>
  `${clamp(value).toFixed(digits)}%`;

export const formatDecimal = (value: unknown, digits = 2): string =>
  safeNumber(value).toFixed(digits);

export const formatTime = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '--';
  const raw = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value;
  const date = typeof raw === 'number'
    ? new Date(raw > 1e12 ? raw : raw * 1000)
    : new Date(String(raw));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN');
};

export const textOrDash = (value: unknown): string =>
  value === null || value === undefined || value === '' ? '--' : String(value);

export const asArray = <T>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];

export const getPath = (value: unknown, path: string, fallback: unknown = 0): unknown => {
  let current: unknown = value;
  for (const key of path.split('.')) {
    if (!current || typeof current !== 'object') return fallback;
    current = (current as Record<string, unknown>)[key];
  }
  return current ?? fallback;
};

export const summarize = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
};
