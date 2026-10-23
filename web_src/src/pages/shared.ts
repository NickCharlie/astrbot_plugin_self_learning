import type { DashboardSnapshot, ReviewItem, UnknownRecord } from '../types/dashboard';
import { asArray, getPath, safeNumber } from '../lib/format';

export const object = (value: unknown): UnknownRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};

export const list = <T>(value: unknown): T[] => {
  if (Array.isArray(value)) return value as T[];
  const record = object(value);
  for (const key of ['items', 'data', 'results', 'updates', 'reviews', 'backups', 'batches', 'dashboards', 'jargon_list']) {
    if (Array.isArray(record[key])) return record[key] as T[];
  }
  return [];
};

export const reviews = (data: DashboardSnapshot, key: string): ReviewItem[] =>
  list<ReviewItem>(data[key]);

// 黑话待审总数：优先读待审接口分页信封的 total（列表被 page_size 截断，
// 数组长度会少算）；兼容旧的纯数组快照，回退为列表长度。
// 待审请求失败时快照为空对象，此时退回 stats 估算，避免误报“队列已清空”。
export const jargonPendingTotal = (data: DashboardSnapshot): number => {
  const payload = data.jargon_reviews;
  if (Array.isArray(payload)) return payload.length;
  const envelope = object(payload);
  const total = envelope.total;
  if (total !== undefined && total !== null && total !== '') return safeNumber(total);
  const rows = list(payload);
  if (rows.length || Object.keys(envelope).length) return rows.length;
  const stats = object(data.jargon_stats);
  const nested = object(stats.data);
  const candidates = safeNumber(stats.total_candidates ?? nested.total_candidates);
  const confirmed = safeNumber(stats.confirmed_jargon ?? nested.confirmed_jargon);
  return Math.max(0, candidates - confirmed);
};

export const metric = (data: DashboardSnapshot, paths: string[], fallback = 0): number => {
  for (const path of paths) {
    const value = getPath(data, path, undefined);
    if (value !== undefined && value !== null) return safeNumber(value, fallback);
  }
  return fallback;
};

export const labelValueRows = (value: unknown): Array<[string, unknown]> =>
  Object.entries(object(value)).filter(([, item]) => typeof item !== 'object').slice(0, 12);
