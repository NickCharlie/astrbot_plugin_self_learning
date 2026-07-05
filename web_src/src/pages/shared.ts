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

export const metric = (data: DashboardSnapshot, paths: string[], fallback = 0): number => {
  for (const path of paths) {
    const value = getPath(data, path, undefined);
    if (value !== undefined && value !== null) return safeNumber(value, fallback);
  }
  return fallback;
};

export const labelValueRows = (value: unknown): Array<[string, unknown]> =>
  Object.entries(object(value)).filter(([, item]) => typeof item !== 'object').slice(0, 12);
