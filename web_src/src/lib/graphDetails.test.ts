import { describe, expect, it } from 'vitest';
import { graphCategoryLabel, graphDetailNodes, graphDetailStats } from './graphDetails';
import { socialToGraph } from './socialGraph';

describe('graph detail panel helpers', () => {
  it('prefers backend stats and data source for the detail readouts', () => {
    expect(graphDetailStats({
      nodes: [{ id: 'a' }],
      links: [],
      groups: ['g1', 'g2'],
      stats: { nodes: 140, links: 230, groups: 3 },
      data_source: 'livingmemory_graph_store',
    })).toEqual([
      ['节点', 140], ['连线', 230], ['群组', 3], ['来源', 'livingmemory_graph_store'],
    ]);
  });

  it('falls back to payload lengths and the self_learning source', () => {
    expect(graphDetailStats({ nodes: [{ id: 'a' }, { id: 'b' }], edges: [{ source: 'a', target: 'b' }] })).toEqual([
      ['节点', 2], ['连线', 1], ['群组', 0], ['来源', 'self_learning'],
    ]);
  });

  it('describes social graphs with their group and source', () => {
    const graph = socialToGraph({ group_id: 'g1', members: [{ user_id: 'u1' }], relations: [] });
    expect(graphDetailStats(graph)).toEqual([['节点', 1], ['连线', 0], ['群组', 1], ['来源', 'social_relations']]);
    expect(graphCategoryLabel(graph.nodes![0])).toBe('成员');
  });

  it('labels node categories and caps the node list at 18', () => {
    expect(graphCategoryLabel({ id: 'a', category: 2, category_name: '概念' })).toBe('概念');
    expect(graphCategoryLabel({ id: 'a', category: 3 })).toBe('3');
    expect(graphCategoryLabel({ id: 'a' })).toBe('节点');
    const nodes = Array.from({ length: 30 }, (_, index) => ({ id: `n${index}` }));
    expect(graphDetailNodes({ nodes })).toHaveLength(18);
  });
});
