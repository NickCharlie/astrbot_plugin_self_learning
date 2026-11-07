import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';
import { reviewBatchLabel, reviewQueueItems } from './ReviewsPage';

// 审查队列双端并集：队列检索、计数徽标、逐条勾选 + 批量作用于选中项、风格审查编辑。

const personaUpdate = { id: '1', review_source: 'traditional', update_type: 'prompt_update', status: 'pending', original_content: '旧', new_content: '新' };
const styleFromPersona = { id: 'style_5', review_source: 'style_learning', update_type: 'style_learning', status: 'pending', reason: '风格描述', proposed_content: 'A: 你好\nB: 你好呀', learned_patterns: ['短句'] };
const styleReview = { id: 5, review_source: 'style_learning', description: '风格描述', few_shots_content: 'A: 你好\nB: 你好呀', learned_patterns: '["短句"]', status: 'pending' };
const jargonCandidate = { id: 9, content: '摸鱼', meaning: '上班时间偷懒', is_confirmed: false, is_complete: false };

describe('reviewQueueItems', () => {
  const queues = { persona: [personaUpdate, styleFromPersona], styleReviews: [styleReview], jargon: [jargonCandidate] };
  const none = { persona: '', style: '', jargon: '' };

  it('keeps style reviews out of the persona queue and prefers persona-sourced style items', () => {
    expect(reviewQueueItems('persona', queues, none).map((item) => item.id)).toEqual(['1']);
    expect(reviewQueueItems('style', queues, none).map((item) => item.id)).toEqual(['style_5']);
    expect(reviewQueueItems('style', { ...queues, persona: [personaUpdate] }, none).map((item) => item.id)).toEqual([5]);
    expect(reviewQueueItems('jargon', queues, none).map((item) => item.id)).toEqual([9]);
  });

  it('reads the server-filtered style list whenever a queue is searched', () => {
    expect(reviewQueueItems('style', queues, { ...none, style: '描述' }).map((item) => item.id)).toEqual([5]);
    expect(reviewQueueItems('style', queues, { ...none, persona: '旧' }).map((item) => item.id)).toEqual([5]);
  });

  it('labels batch buttons by scope', () => {
    expect(reviewBatchLabel('approve', false)).toBe('全部通过');
    expect(reviewBatchLabel('reject', true)).toBe('驳回所选');
    expect(reviewBatchLabel('delete', true)).toBe('删除所选');
  });
});

const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('reviews page', () => {
  const requests: string[] = [];
  const posts: Array<{ url: string; method: string; body: unknown }> = [];

  beforeEach(() => {
    localStorage.clear();
    requests.length = 0;
    posts.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      if (method !== 'GET') {
        posts.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
        return json({ success: true, message: 'ok' });
      }
      requests.push(url);
      if (url.includes('/api/persona_updates/reviewed')) return json({ updates: [], total: 0 });
      if (url.includes('/api/persona_updates')) return json({ success: true, updates: [personaUpdate], total: 1 });
      if (url.includes('/api/style_learning/reviews')) return json({ reviews: [styleReview], total: 1 });
      if (url.includes('/api/jargon/list')) return json({ success: true, jargon_list: [jargonCandidate], total: 1, data: [jargonCandidate] });
      return json({});
    });
    window.location.hash = '#/reviews';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('loads 50-item queues, searches each queue and shows count badges', async () => {
    render(() => <App />);
    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    expect(requests.some((url) => url.includes('/api/persona_updates?limit=50'))).toBe(true);
    expect(requests.some((url) => url.includes('/api/jargon/list?page=1&page_size=50&confirmed=false&pending=true'))).toBe(true);

    const input = screen.getByPlaceholderText('搜索黑话候选');
    fireEvent.input(input, { target: { value: '摸' } });
    fireEvent.click(within(input.closest('section')!).getByRole('button', { name: '搜索' }));
    await waitFor(() => expect(requests.some((url) => url.includes('/api/jargon/list') && url.includes('keyword=%E6%91%B8'))).toBe(true));
  });

  it('confirms batch actions on the whole queue or only the selected cards', async () => {
    render(() => <App />);
    expect(await screen.findByText('摸鱼')).toBeInTheDocument();
    const jargonPanel = screen.getByText('黑话审查').closest('section')!;
    expect(within(jargonPanel).getByRole('button', { name: '全部通过' })).toBeInTheDocument();

    fireEvent.click(within(jargonPanel).getByRole('checkbox', { name: '选择' }));
    expect(await within(jargonPanel).findByRole('button', { name: '通过所选' })).toBeInTheDocument();
    expect(within(jargonPanel).getByText('1/1')).toBeInTheDocument();

    fireEvent.click(within(jargonPanel).getByRole('button', { name: '通过所选' }));
    expect(await screen.findByText('确定对选中的 1 条黑话审查执行通过吗？')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认' }));
    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/jargon/batch_review'))).toBe(true));
    expect(posts.find((post) => post.url.includes('/api/jargon/batch_review'))?.body).toEqual({ jargon_ids: [9], action: 'approve' });

    const personaPanel = screen.getByText('待审人格').closest('section')!;
    fireEvent.click(within(personaPanel).getByRole('button', { name: '全部驳回' }));
    expect(await screen.findByText('确定对当前 1 条待审人格执行驳回吗？')).toBeInTheDocument();
  });

  it('edits a style review through the shared update endpoint', async () => {
    render(() => <App />);
    expect(await screen.findByText('风格描述')).toBeInTheDocument();
    const stylePanel = screen.getByText('风格审查').closest('section')!;
    fireEvent.click(within(stylePanel).getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑表达方式' });
    fireEvent.input(within(dialog).getByLabelText('描述'), { target: { value: '新的描述' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(posts.some((post) => post.method === 'PUT')).toBe(true));
    const put = posts.find((post) => post.method === 'PUT')!;
    expect(put.url).toContain('/api/style_learning/reviews/5');
    expect(put.body).toEqual({ description: '新的描述', few_shots_content: 'A: 你好\nB: 你好呀', learned_patterns: ['短句'] });
  });
});
