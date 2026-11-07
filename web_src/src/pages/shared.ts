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

// 待办总量：人格待审 + 风格待审 + 黑话待审，均读分页 total。人格待审首屏混入风格审查
// （review_source === 'style_learning'）时扣除风格部分，避免与风格待审重复计数。
// 首页「待办总量 / 审查队列」与 AI 巡检「审查队列存在积压」同源（内嵌页 reviewBacklog 同口径）。
export const reviewBacklog = (data: DashboardSnapshot) => {
  const personaItems = reviews(data, 'persona_updates');
  const personaTotal = safeNumber(object(data.persona_updates).total, personaItems.length);
  const styleTotal = safeNumber(object(data.style_learning_reviews).total, reviews(data, 'style_learning_reviews').length);
  const personaIncludesStyle = personaItems.some((item) => item.review_source === 'style_learning');
  const personaPending = personaIncludesStyle ? Math.max(0, personaTotal - styleTotal) : personaTotal;
  const jargonPending = jargonPendingTotal(data);
  return { personaPending, styleTotal, jargonPending, total: personaPending + styleTotal + jargonPending };
};

// 智能指标综合评分：0-1 视为比例换算为百分制，夹在 0-100（与内嵌页 normalizeScore 同口径）
export const intelligenceScore = (data: DashboardSnapshot) => {
  const intelligence = object(data.intelligence);
  const raw = safeNumber(intelligence.overall_score);
  return {
    score: Math.max(0, Math.min(100, raw <= 1 ? raw * 100 : raw)),
    dimensions: Object.keys(object(intelligence.dimensions)).length,
  };
};

// 健康检查等明细对象：取前 3 项 key: value，以 · 连接（与内嵌页 detailText 同口径）
export const detailText = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value !== 'object') return String(value);
  const entries = Object.entries(value as UnknownRecord).slice(0, 3);
  if (!entries.length) return '--';
  return entries
    .map(([key, item]) => `${key}: ${item !== null && typeof item === 'object' ? JSON.stringify(item) : String(item)}`)
    .join(' · ');
};

export const labelValueRows = (value: unknown): Array<[string, unknown]> =>
  Object.entries(object(value)).filter(([, item]) => typeof item !== 'object').slice(0, 12);

/** JSON 文本框：解析失败时按行拆分（与内嵌插件页 parseModalJson 同口径，用于学习模式 / 开场对话编辑）。 */
export const parseJsonOrLines = (raw: string): unknown => {
  const text = raw.trim();
  if (!text) return [];
  try { return JSON.parse(text); } catch { return text.split(/\n+/).map((line) => line.trim()).filter(Boolean); }
};
