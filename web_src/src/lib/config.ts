import type { ConfigField } from '../types/dashboard';

export function normalizeFieldValue(field: ConfigField, value: unknown): unknown {
  if (field.type === 'boolean' || field.type === 'bool' || field.widget === 'switch' || field.widget === 'toggle') {
    return value === true || value === 'true' || value === 1 || value === '1';
  }
  if (field.type === 'integer' || field.type === 'int') {
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : field.default ?? 0;
  }
  if (field.type === 'number' || field.type === 'float') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : field.default ?? 0;
  }
  if (field.type === 'array' && typeof value === 'string') {
    return value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
  }
  if (field.type === 'json' && typeof value === 'string') {
    try { return JSON.parse(value); } catch { return value; }
  }
  return value ?? '';
}

export const configValuesEqual = (field: ConfigField, left: unknown, right: unknown): boolean =>
  JSON.stringify(normalizeFieldValue(field, left)) === JSON.stringify(normalizeFieldValue(field, right));
