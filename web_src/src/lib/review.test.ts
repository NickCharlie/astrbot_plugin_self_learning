import { describe, expect, it } from 'vitest';
import {
  formatDialogLines, reviewAfterPrompt, reviewBeforePrompt, reviewBeginDialogs,
  reviewChangeMeta, reviewChangePreview, reviewHasChange,
} from './review';

describe('review change preview parsing', () => {
  it('reads before/after prompts from the nested change_preview payload', () => {
    const item = {
      id: 'persona_learning_7',
      change_preview: {
        before_system_prompt: '旧提示词',
        after_system_prompt: '旧提示词\n\n新增加的特征',
        application_mode: 'append_system_prompt',
        target_fields: ['system_prompt'],
        group_id: 'group-1',
      },
    };

    expect(reviewChangePreview(item).application_mode).toBe('append_system_prompt');
    expect(reviewBeforePrompt(item)).toBe('旧提示词');
    expect(reviewAfterPrompt(item)).toBe('旧提示词\n\n新增加的特征');
    expect(reviewHasChange(item)).toBe(true);
    expect(reviewChangeMeta(item)).toEqual([
      '应用方式：append_system_prompt',
      '影响字段：system_prompt',
      '群组：group-1',
    ]);
  });

  it('falls back to change_snapshot for reviewed records', () => {
    const item = {
      id: 3,
      status: 'approved',
      change_snapshot: {
        before_system_prompt: 'before',
        after_system_prompt: 'after',
      },
    };

    expect(reviewBeforePrompt(item)).toBe('before');
    expect(reviewAfterPrompt(item)).toBe('after');
  });

  it('falls back to top-level original_content/new_content when no preview exists', () => {
    const item = { id: 5, original_content: '原人格', new_content: '新人格' };

    expect(reviewBeforePrompt(item)).toBe('原人格');
    expect(reviewAfterPrompt(item)).toBe('新人格');
  });

  it('exposes begin dialog diffs for style learning reviews', () => {
    const item = {
      id: 'style_9',
      change_preview: {
        before_system_prompt: 'same prompt',
        after_system_prompt: 'same prompt',
        before_begin_dialogs: ['用户: 在吗'],
        after_begin_dialogs: ['用户: 在吗', '用户: 早呀', 'Bot: 早呀'],
      },
    };

    expect(reviewBeginDialogs(item)).toEqual({
      before: ['用户: 在吗'],
      after: ['用户: 在吗', '用户: 早呀', 'Bot: 早呀'],
    });
    // prompt 没有变化，但示例对话有新增，仍应展示变更详情
    expect(reviewHasChange(item)).toBe(true);
    expect(formatDialogLines(reviewBeginDialogs(item).after).split('\n')).toHaveLength(3);
  });

  it('falls back to top-level content for legacy content-only records', () => {
    const item = { id: 6, content: '只有待审文本的记录' };

    expect(reviewAfterPrompt(item)).toBe('只有待审文本的记录');
    expect(reviewHasChange(item)).toBe(true);
  });

  it('reports no change for a record without any preview content', () => {
    expect(reviewHasChange({ id: 1 })).toBe(false);
  });
});
