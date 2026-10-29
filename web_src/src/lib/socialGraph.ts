import type { GraphPayload } from '../types/dashboard';

export type SocialGroup = Record<string, unknown>;

export const socialGroupId = (group: SocialGroup): string =>
  String(group.group_id ?? group.id ?? '');

export const socialGroupName = (group: SocialGroup): string =>
  String(group.group_name ?? group.name ?? socialGroupId(group));

/** 把 /api/social_relations/<group> 的成员/关系转换为 GraphView 需要的 nodes/links。 */
export const socialToGraph = (data: Record<string, unknown>): GraphPayload => {
  const members = Array.isArray(data.members) ? data.members as Record<string, unknown>[] : [];
  const relations = Array.isArray(data.relations) ? data.relations as Record<string, unknown>[] : [];
  return {
    nodes: members.map((member) => ({
      id: String(member.user_id ?? member.id ?? ''),
      name: String(member.nickname ?? member.user_id ?? ''),
      value: Number(member.message_count) || 1,
      category: 'member',
    })),
    links: relations.map((relation) => ({
      source: String(relation.source ?? ''),
      target: String(relation.target ?? ''),
      value: Number(relation.strength) || 0,
    })),
    categories: [{ name: 'member' }],
  };
};
