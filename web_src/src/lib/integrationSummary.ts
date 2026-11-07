import type { UnknownRecord } from '../types/dashboard';
import { formatCount, safeNumber } from './format';

const object = (value: unknown): UnknownRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};

/** 人类可读结果摘要 + 原始 JSON（与内嵌页各 renderXxxPreview 同口径）。 */
export const summarizeWithJson = (lines: string[], data: unknown): string => {
  const body = lines.length ? `${lines.join('\n')}\n\n` : '';
  let json = '';
  try {
    json = JSON.stringify(data, null, 2);
  } catch {
    json = String(data);
  }
  return `${body}${json}`;
};

const count = (value: unknown): string => formatCount(safeNumber(value));

/** MaiBot 迁移预览/导入摘要（预览统计 / 审查去向 / 分类去向）。 */
export const maibotSummaryLines = (data: UnknownRecord): string[] => {
  const counts = object(data.counts);
  const breakdown = object(data.review_breakdown);
  const destinations = object(data.destinations);
  const lines: string[] = [];
  if (Object.keys(counts).length) {
    lines.push(
      `预览: 表达 ${count(counts.expressions)} · 黑话 ${count(counts.jargons)} · 记忆 ${count(counts.memories)}`,
    );
  }
  if (Object.keys(breakdown).length) {
    lines.push(
      `导入: 表达审查 ${count(breakdown.style_learning_reviews)} · 黑话候选 ${count(breakdown.jargon_candidates)} · 记忆审查 ${count(breakdown.persona_memory_reviews)}`,
    );
  }
  if (Object.keys(destinations).length) {
    lines.push(
      `分类去向: 表达 -> ${destinations.expressions}; 黑话 -> ${destinations.jargons}; 记忆 -> ${destinations.memories}`,
    );
  }
  return lines;
};

/** 世界书预览/导入摘要（名称 / 条目统计 / 字符与 Tokens / 去向 / 导入结果）。 */
export const worldbookSummaryLines = (data: UnknownRecord): string[] => {
  const counts = object(data.counts);
  const breakdown = object(data.review_breakdown);
  const lines: string[] = [];
  if (data.name) lines.push(`世界书：${String(data.name)}`);
  if (Object.keys(counts).length) {
    lines.push(
      `预览: 条目 ${count(counts.entries)}（启用 ${count(counts.enabled_entries)} / 禁用 ${count(counts.disabled_entries)}）· 关键词 ${count(counts.keywords)}`,
    );
    lines.push(`字符 ${count(counts.content_chars)} · 预估 Tokens ${count(counts.estimated_tokens)}`);
  }
  if (Object.keys(breakdown).length) {
    lines.push(
      `去向: 记忆审查 ${count(breakdown.persona_memory_reviews)} · 黑话候选 ${count(breakdown.jargon_candidates)} · 图谱实体 ${count(breakdown.knowledge_graph_entities)}`,
    );
  }
  if (data.entries_imported !== undefined) {
    lines.push(
      `导入: 条目 ${count(data.entries_imported)} · 记忆 ${count(data.memory_reviews_imported)} · 黑话 ${count(data.jargons_imported)} · 图谱实体/关系 ${count(data.kg_entities_imported)}/${count(data.kg_relations_imported)} · 跳过 ${count(data.skipped)}`,
    );
  }
  return lines;
};

/** QQ 聊天记录预览/导入摘要（消息统计 / 字符 Tokens / 导入结果 / 去向）。 */
export const qchatSummaryLines = (data: UnknownRecord): string[] => {
  const counts = object(data.counts);
  const destinations = object(data.destinations);
  const lines: string[] = [];
  if (Object.keys(counts).length) {
    lines.push(
      `预览: 消息 ${count(counts.messages)} · Bot ${count(counts.bot_messages)} · 发送者 ${count(counts.unique_senders)}`,
    );
    lines.push(`字符 ${count(counts.content_chars)} · 预估 Tokens ${count(counts.estimated_tokens)}`);
  }
  if (data.messages_imported !== undefined || data.messages_seen !== undefined) {
    lines.push(
      `导入: 扫描 ${count(data.messages_seen)} · 写入 ${count(data.messages_imported)} · 重复 ${count(data.duplicate_messages)}`,
    );
  }
  if (Object.keys(destinations).length) {
    lines.push(
      `去向: 原始消息 -> ${destinations.raw_messages || 'raw_messages'}; 学习队列 -> ${destinations.learning_queue || 'raw_messages.processed=false'}`,
    );
  }
  return lines;
};
