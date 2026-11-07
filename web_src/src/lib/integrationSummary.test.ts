import { describe, expect, it } from 'vitest';
import { maibotSummaryLines, qchatSummaryLines, summarizeWithJson, worldbookSummaryLines } from './integrationSummary';

// 内嵌页的世界书 / MaiBot / QQ 摘要行此前只有内嵌版有，移植到独立版后两端共用口径。

describe('integration result summaries', () => {
  it('summarizes maibot preview counts and destinations', () => {
    const lines = maibotSummaryLines({
      counts: { expressions: 2, jargons: 1, memories: 3 },
      destinations: { expressions: 'style_learning', jargons: 'jargon', memories: 'persona_review' },
    });
    expect(lines).toEqual([
      '预览: 表达 2 · 黑话 1 · 记忆 3',
      '分类去向: 表达 -> style_learning; 黑话 -> jargon; 记忆 -> persona_review',
    ]);
  });

  it('summarizes worldbook preview and import results', () => {
    const preview = worldbookSummaryLines({
      name: '测试世界书',
      counts: { entries: 2, enabled_entries: 1, disabled_entries: 1, keywords: 4, content_chars: 120, estimated_tokens: 60 },
    });
    expect(preview[0]).toBe('世界书：测试世界书');
    expect(preview[1]).toContain('条目 2（启用 1 / 禁用 1）');
    const imported = worldbookSummaryLines({ entries_imported: 2, memory_reviews_imported: 1, jargons_imported: 2, kg_entities_imported: 3, kg_relations_imported: 2, skipped: 1 });
    expect(imported).toEqual(['导入: 条目 2 · 记忆 1 · 黑话 2 · 图谱实体/关系 3/2 · 跳过 1']);
  });

  it('summarizes qq chat import results', () => {
    const lines = qchatSummaryLines({
      counts: { messages: 10, bot_messages: 2, unique_senders: 3, content_chars: 400, estimated_tokens: 200 },
      messages_seen: 10, messages_imported: 8, duplicate_messages: 2,
      destinations: { raw_messages: 'raw_messages' },
    });
    expect(lines).toHaveLength(4);
    expect(lines[2]).toBe('导入: 扫描 10 · 写入 8 · 重复 2');
    expect(lines[3]).toContain('raw_messages');
  });

  it('appends raw json only when a result exists', () => {
    const text = summarizeWithJson(['预览: 表达 1'], { counts: { expressions: 1 } });
    expect(text).toContain('预览: 表达 1');
    expect(text).toContain('"expressions": 1');
    expect(summarizeWithJson([], { a: 1 })).toBe('{\n  "a": 1\n}');
  });
});
