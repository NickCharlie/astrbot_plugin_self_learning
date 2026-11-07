import type { GraphNode, GraphPayload } from '../types/dashboard';
import { safeNumber } from './format';

/** 图谱详情面板最多列出的节点数（与内嵌页一致）。 */
export const GRAPH_DETAIL_NODE_LIMIT = 18;

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

/** 节点 / 连线 / 群组优先取后端 stats，来源取 data_source（与内嵌页 graphDetailStats 同口径）。 */
export const graphDetailStats = (payload: GraphPayload): Array<[string, number | string]> => {
  const stats = record(payload.stats);
  const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
  const links = Array.isArray(payload.links) ? payload.links : Array.isArray(payload.edges) ? payload.edges : [];
  const groups = Array.isArray(payload.groups) ? payload.groups : [];
  return [
    ['节点', safeNumber(stats.nodes ?? nodes.length)],
    ['连线', safeNumber(stats.links ?? links.length)],
    ['群组', safeNumber(stats.groups ?? groups.length)],
    ['来源', String(payload.data_source || 'self_learning')],
  ];
};

/** 节点分类标签：category_name 优先；社交成员显示「成员」；缺省为「节点」。 */
export const graphCategoryLabel = (node: GraphNode): string => {
  if (node.category_name) return String(node.category_name);
  if (node.category === 'member') return '成员';
  return node.category !== undefined && node.category !== null && node.category !== ''
    ? String(node.category)
    : '节点';
};

export const graphDetailNodes = (payload: GraphPayload): GraphNode[] =>
  (Array.isArray(payload.nodes) ? payload.nodes : []).slice(0, GRAPH_DETAIL_NODE_LIMIT);
