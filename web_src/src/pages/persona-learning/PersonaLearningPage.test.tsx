import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// issue #280：人格审核的修改内容与人格备份详情必须能在 WebUI 中查看。

const pendingReview = {
  id: 1,
  update_type: 'prompt_update',
  review_source: 'traditional',
  status: 'pending',
  group_id: 'g1',
  created_at: 1792500000,
  original_content: '旧提示词',
  new_content: '新提示词',
  change_preview: {
    before_system_prompt: '旧提示词',
    after_system_prompt: '新提示词',
    application_mode: 'replace_system_prompt',
    target_fields: ['system_prompt'],
    group_id: 'g1',
    proposed_content: '新提示词',
  },
};

const reviewedRecord = {
  id: 'persona_learning_2',
  update_type: 'persona_learning',
  review_source: 'persona_learning',
  status: 'approved',
  review_time: 1792500000,
  proposed_content: '追加的人格特征',
};

const backupSummary = {
  id: 3,
  backup_name: '备份A',
  group_id: 'g1',
  timestamp: 1792500000,
  reason: '自动备份',
};

const backupDetail = {
  ...backupSummary,
  summary: { backup_name: '备份A', group_id: 'g1', timestamp: 1792500000, reason: '自动备份' },
  original_persona: { name: '测试人格', prompt: '备份中的旧提示词' },
  imitation_dialogues: ['用户: 你好', 'Bot: 你好呀'],
};

const personaRecord = {
  persona_id: 'p1',
  name: '测试人格',
  system_prompt: '人格提示词',
  begin_dialogs: ['用户: hi'],
  tools: [],
};

const json = (payload: unknown) => new Response(
  JSON.stringify(payload),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
);

let revertCalls = 0;

const installFetch = () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method === 'POST' && url.includes('/api/persona_updates/persona_learning_2/revert')) {
      revertCalls += 1;
      return json({ success: true, message: '已撤回' });
    }
    if (url.includes('/api/persona_updates/reviewed')) return json({ updates: [reviewedRecord], total: 1 });
    if (url.includes('/api/persona_updates')) return json({ updates: [pendingReview], total: 1 });
    if (url.includes('/api/persona_backups/list')) return json({ backups: [backupSummary], total: 1 });
    if (url.includes('/api/persona_backups/3')) return json(backupDetail);
    if (url.includes('/api/persona_management/list')) return json({ personas: [personaRecord] });
    if (url.includes('/api/persona_management/get/p1')) return json(personaRecord);
    if (url.includes('/api/persona_management/current')) {
      return json({ group_id: 'default', persona: { name: '当前人格', persona_id: 'p1' }, prompt_preview: '当前提示词' });
    }
    return json({});
  });
};

describe('persona review and backup visibility (issue #280)', () => {
  beforeEach(() => {
    localStorage.clear();
    revertCalls = 0;
    installFetch();
    window.location.hash = '#/persona-learning';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows backup content in a detail dialog instead of a toast only', async () => {
    render(() => <App />);

    expect(await screen.findByText('备份A')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看备份' }));

    expect(await screen.findByRole('dialog', { name: '备份详情' })).toBeInTheDocument();
    expect(screen.getByText('备份中的旧提示词')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '备份详情' }).textContent).toContain('用户: 你好');
  });

  it('expands the nested change_preview when reviewing a pending update', async () => {
    render(() => <App />);

    const toggle = await screen.findByText('查看变更详情');
    fireEvent.click(toggle);

    expect(await screen.findByText(/应用方式：replace_system_prompt/)).toBeInTheDocument();
    expect(screen.getByText(/影响字段：system_prompt/)).toBeInTheDocument();
    const diffText = document.body.textContent ?? '';
    expect(diffText).toContain('旧提示词');
    expect(diffText).toContain('新提示词');
  });

  it('lists reviewed persona updates and can revert them', async () => {
    render(() => <App />);

    expect(await screen.findByText('追加的人格特征')).toBeInTheDocument();
    expect(screen.getByText('已通过')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '撤回' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认撤回' }));

    await waitFor(() => expect(revertCalls).toBe(1));
  });

  it('lists personas and opens the full persona prompt', async () => {
    render(() => <App />);

    expect(await screen.findByText('测试人格')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看人格' }));

    expect(await screen.findByRole('dialog', { name: '人格详情' })).toBeInTheDocument();
    expect(screen.getByText('人格提示词')).toBeInTheDocument();
  });
});
