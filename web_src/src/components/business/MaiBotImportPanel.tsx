import { createSignal, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { object } from '../../pages/shared';
import { summarize } from '../../lib/format';
import { Button, Input, Panel, Textarea } from '../ui';
import styles from './MaiBotImportPanel.module.scss';

// 后端已提供 /api/integrations/maibot-learning/{preview,import,export}，
// 但 WebUI 只有世界书和 QQ 聊天记录入口，MaiBot 迁移能力一直不可见。
export function MaiBotImportPanel() {
  const dashboard = useDashboard();
  const [root, setRoot] = createSignal('');
  const [dbPath, setDbPath] = createSignal('');
  const [memorixPath, setMemorixPath] = createSignal('');
  const [payloadText, setPayloadText] = createSignal('');
  const [group, setGroup] = createSignal('global');
  const [importExpressions, setImportExpressions] = createSignal(true);
  const [importJargons, setImportJargons] = createSignal(true);
  const [importMemories, setImportMemories] = createSignal(true);
  const [approveChecked, setApproveChecked] = createSignal(true);
  const [busy, setBusy] = createSignal('');
  const [result, setResult] = createSignal<unknown>(null);

  const sourceBody = (): Record<string, unknown> => {
    const text = payloadText().trim();
    if (text) {
      const payload = JSON.parse(text);
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error('MaiBot 导出 JSON 必须是对象');
      }
      return { payload };
    }
    const body: Record<string, unknown> = {};
    if (root().trim()) body.maibot_root = root().trim();
    if (dbPath().trim()) body.db_path = dbPath().trim();
    if (memorixPath().trim()) body.memorix_db_path = memorixPath().trim();
    if (!body.maibot_root && !body.db_path) {
      throw new Error('请填写 MaiBot 根目录或数据库路径，或粘贴导出 JSON');
    }
    return body;
  };

  const downloadJson = (data: unknown, filename: string) => {
    const text = JSON.stringify(data, null, 2);
    const blob = new Blob([text], { type: 'application/json' });
    const canObjectUrl = typeof URL.createObjectURL === 'function';
    const href = canObjectUrl ? URL.createObjectURL(blob) : `data:application/json;charset=utf-8,${encodeURIComponent(text)}`;
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    if (canObjectUrl) URL.revokeObjectURL(href);
  };

  const run = async (action: 'preview' | 'import' | 'export') => {
    let source: Record<string, unknown>;
    try { source = sourceBody(); }
    catch (caught) {
      return dashboard.toast(caught instanceof Error ? caught.message : '来源参数无效', 'warning');
    }
    if (action === 'import' && !await dashboard.confirm({
      title: '导入 MaiBot 学习数据',
      message: '将写入表达样本、黑话候选和记忆数据，重复内容会被跳过。确定继续吗？',
      tone: 'warning',
      confirmText: '确认导入',
    })) return;
    setBusy(action);
    setResult(null);
    try {
      const response = await api.post<{ success?: boolean; data?: unknown }>(`/api/integrations/maibot-learning/${action}`, {
        ...source,
        ...(action === 'export' ? {} : {
          default_group_id: group().trim() || 'global',
          import_expressions: importExpressions(),
          import_jargons: importJargons(),
          import_memories: importMemories(),
          approve_checked_expressions: approveChecked(),
        }),
      });
      const data = response.data ?? response;
      if (action === 'export') {
        downloadJson(data, 'maibot-learning-export.json');
        dashboard.toast('MaiBot 学习数据已导出', 'success');
      } else {
        setResult(data);
        // 导入接口即使部分条目失败也返回 HTTP 200，失败信息只在包体里
        const payload = object(data);
        const errors = Array.isArray(payload.errors) ? payload.errors : [];
        const failed = action === 'import' && (payload.success === false || errors.length > 0);
        dashboard.toast(
          failed ? '导入部分失败，请查看下方明细' : action === 'preview' ? '预览完成' : '导入完成',
          failed ? 'warning' : 'success',
        );
        if (action === 'import') await dashboard.refresh(true);
      }
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : 'MaiBot 学习数据操作失败', 'danger');
    } finally { setBusy(''); }
  };

  return (
    <Panel
      title="MaiBot 学习数据"
      hint="从 MaiBot 数据库或导出 JSON 迁移表达样本、黑话与记忆；导出不会修改数据"
      icon="swap_horiz"
    >
      <div class={styles['source-grid']}>
        <Input label="MaiBot 根目录" placeholder="MaiBot 安装目录（可留空）" value={root()} onInput={(event) => setRoot(event.currentTarget.value)} />
        <Input label="MaiBot 数据库路径" placeholder="直接指定 SQLite 数据库（可留空）" value={dbPath()} onInput={(event) => setDbPath(event.currentTarget.value)} />
        <Input label="Memorix 数据库路径（可选）" value={memorixPath()} onInput={(event) => setMemorixPath(event.currentTarget.value)} />
        <Input label="导入群组" placeholder="global" value={group()} onInput={(event) => setGroup(event.currentTarget.value)} />
      </div>
      <Textarea
        label="或粘贴 MaiBot 导出 JSON"
        rows={6}
        value={payloadText()}
        onInput={(event) => setPayloadText(event.currentTarget.value)}
        placeholder={'{"version": 1, "sessions": [], "expressions": [], "jargons": [], "memories": []}'}
      />
      <div class={styles['option-grid']}>
        <label><input type="checkbox" checked={importExpressions()} onChange={(event) => setImportExpressions(event.currentTarget.checked)} /> 导入表达样本</label>
        <label><input type="checkbox" checked={importJargons()} onChange={(event) => setImportJargons(event.currentTarget.checked)} /> 导入黑话候选</label>
        <label><input type="checkbox" checked={importMemories()} onChange={(event) => setImportMemories(event.currentTarget.checked)} /> 导入记忆</label>
        <label><input type="checkbox" checked={approveChecked()} onChange={(event) => setApproveChecked(event.currentTarget.checked)} /> 已勾选表达直接通过审查</label>
      </div>
      <div class="inline-actions">
        <Button loading={busy() === 'preview'} onClick={() => run('preview')}>预览</Button>
        <Button tone="primary" loading={busy() === 'import'} onClick={() => run('import')}>导入</Button>
        <Button icon="download" loading={busy() === 'export'} onClick={() => run('export')}>导出 JSON</Button>
      </div>
      <Show when={result()}><pre class={styles['result-box']}>{summarize(result())}</pre></Show>
    </Panel>
  );
}
