import { describe, expect, it } from 'vitest';
import { socialGroupId, socialGroupName, socialToGraph } from './socialGraph';

describe('social graph mapping', () => {
  it('maps members and relations to graph nodes and links', () => {
    const graph = socialToGraph({
      members: [
        { user_id: 'u1', nickname: '小明', message_count: 5 },
        { user_id: 'u2', nickname: '小红', message_count: 3 },
      ],
      relations: [{ source: 'u1', target: 'u2', strength: 0.8 }],
    });

    expect(graph.nodes).toEqual([
      { id: 'u1', name: '小明', value: 5, category: 'member' },
      { id: 'u2', name: '小红', value: 3, category: 'member' },
    ]);
    expect(graph.links).toEqual([{ source: 'u1', target: 'u2', value: 0.8 }]);
    expect(graph.categories).toEqual([{ name: 'member' }]);
  });

  it('defaults missing member fields without dropping the node', () => {
    const graph = socialToGraph({ members: [{}], relations: [{}] });

    expect(graph.nodes?.[0]).toEqual({ id: '', name: '', value: 1, category: 'member' });
    expect(graph.links?.[0]).toEqual({ source: '', target: '', value: 0 });
  });

  it('reads group id and name from either payload shape', () => {
    expect(socialGroupId({ group_id: 'g1' })).toBe('g1');
    expect(socialGroupId({ id: 'g2' })).toBe('g2');
    expect(socialGroupName({ group_id: 'g1' })).toBe('g1');
    expect(socialGroupName({ name: '测试群' })).toBe('测试群');
  });
});
