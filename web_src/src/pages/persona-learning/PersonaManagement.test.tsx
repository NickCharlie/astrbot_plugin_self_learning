import { cleanup, fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';

// 人格学习双端并集：当前人格读数卡、人格列表编辑 / 删除（删除先确认）、「刷新人格」。

const personaRecord = {
  persona_id: 'p1',
  name: '测试人格',
  system_prompt: '人格提示词',
  begin_dialogs: ['用户: hi'],
  tools: [],
};

const json = (payload: unknown) => new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('persona list editing and current readouts', () => {
  const posts: Array<{ url: string; body: unknown }> = [];

  beforeEach(() => {
    localStorage.clear();
    posts.length = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if ((init?.method ?? 'GET') !== 'GET') {
        posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return json({ message: 'ok' });
      }
      if (url.includes('/api/persona_management/list')) return json({ personas: [personaRecord] });
      if (url.includes('/api/persona_management/current')) {
        return json({ group_id: 'default', persona: { name: '当前人格', persona_id: 'p1' }, prompt_preview: '当前提示词', prompt_length: 120, begin_dialog_count: 2, tool_count: 1, degraded: false });
      }
      if (url.includes('/api/persona_backups/list')) return json({ backups: [{ id: 3, backup_name: '备份A' }], total: 1 });
      return json({});
    });
    window.location.hash = '#/persona-learning';
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows the current persona readouts and the fixed refresh label', async () => {
    render(() => <App />);
    expect(await screen.findByText('当前人格', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByText('提示词字数').closest('.slx-stat')?.textContent).toContain('120');
    expect(screen.getByText('当前群组').closest('.slx-stat')?.textContent).toContain('default');
    expect(screen.getByRole('button', { name: '刷新人格' })).toBeInTheDocument();
    expect(screen.queryByText('刷新人格式')).not.toBeInTheDocument();
  });

  it('edits a persona through the update endpoint', async () => {
    render(() => <App />);
    expect(await screen.findByText('测试人格')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '编辑人格' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑人格' });
    fireEvent.input(within(dialog).getByLabelText('名称'), { target: { value: '新名字' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/persona_management/update/p1'))).toBe(true));
    expect(posts.find((post) => post.url.includes('/update/p1'))?.body).toEqual({
      persona_id: 'p1',
      name: '新名字',
      system_prompt: '人格提示词',
      prompt: '人格提示词',
      begin_dialogs: ['用户: hi'],
    });
    expect(await screen.findByText('人格已更新')).toBeInTheDocument();
  });

  it('asks for confirmation before deleting a persona', async () => {
    render(() => <App />);
    expect(await screen.findByText('测试人格')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除人格' }));
    expect(await screen.findByText('确定删除人格“测试人格”吗？此操作不可撤销。')).toBeInTheDocument();
    expect(posts).toHaveLength(0);
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: '删除' }));
    await waitFor(() => expect(posts.some((post) => post.url.includes('/api/persona_management/delete/p1'))).toBe(true));
    expect(await screen.findByText('人格已删除')).toBeInTheDocument();
  });
});
