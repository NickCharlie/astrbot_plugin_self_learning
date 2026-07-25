import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object } from '../shared';
import type { IntegrationItem } from '../../types/dashboard';
import { summarize } from '../../lib/format';
import { resolveHostUrl } from '../../lib/routing';
import { IntegrationCard } from '../../components/business/IntegrationCard';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, Input, Panel, Select, Textarea } from '../../components/ui';
import styles from './IntegrationsPage.module.scss';

export function IntegrationsPage() {
  const dashboard = useDashboard();
  const [worldbookJson, setWorldbookJson] = createSignal('');
  const [worldbookGroup, setWorldbookGroup] = createSignal('global');
  const [importMemories, setImportMemories] = createSignal(true);
  const [importJargons, setImportJargons] = createSignal(true);
  const [importKnowledge, setImportKnowledge] = createSignal(true);
  const [includeDisabled, setIncludeDisabled] = createSignal(false);
  const [worldbookResult, setWorldbookResult] = createSignal<unknown>(null);
  const [worldbookHistory, setWorldbookHistory] = createSignal<Record<string, unknown>[]>([]);
  const [qchatPath, setQchatPath] = createSignal('');
  const [qchatGroup, setQchatGroup] = createSignal('');
  const [qchatMax, setQchatMax] = createSignal('100000');
  const [trainingPairs, setTrainingPairs] = createSignal(true);
  const [qchatResult, setQchatResult] = createSignal<unknown>(null);
  const [qchatShadowSender, setQchatShadowSender] = createSignal('');
  const [busy, setBusy] = createSignal('');
  const qchatData = () => {
    const result = object(qchatResult());
    return object(result.data ?? result);
  };
  const qchatSenders = () => list<Record<string, unknown>>(qchatData().senders);
  const integrations = () => list<IntegrationItem>(
    dashboard.integrations()?.dashboards
    ?? dashboard.integrations()?.integrations
    ?? dashboard.integrations()?.items
    ?? dashboard.integrations(),
  );
  const loadWorldbookHistory = async () => {
    try {
      const payload = await api.get<Record<string, unknown>>('/api/integrations/worldbook/imports?limit=8');
      const data = object(payload.data);
      setWorldbookHistory(list<Record<string, unknown>>(data.imports ?? data.items ?? data));
    } catch {
      setWorldbookHistory([]);
    }
  };
  onMount(loadWorldbookHistory);
  const worldbook = async (action: 'preview' | 'import') => {
    let data: unknown;
    try { data = JSON.parse(worldbookJson()); } catch { return dashboard.toast('世界书 JSON 格式无效', 'warning'); }
    setBusy(`worldbook-${action}`);
    try {
      if (action === 'import' && !await dashboard.confirm({ title: '导入世界书', message: '将写入人格审查、黑话候选或知识图谱，确定继续吗？', tone: 'warning', confirmText: '确认导入' })) return;
      const result = await api.post(`/api/integrations/worldbook/${action}`, {
        payload: data,
        default_group_id: worldbookGroup() || 'global',
        import_memories: importMemories(),
        import_jargons: importJargons(),
        import_knowledge_graph: importKnowledge(),
        include_disabled: includeDisabled(),
      });
      setWorldbookResult(result); dashboard.toast(action === 'preview' ? '预览完成' : '导入完成', 'success');
      if (action === 'import') await loadWorldbookHistory();
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '世界书操作失败', 'danger'); }
    finally { setBusy(''); }
  };
  const qchat = async (action: 'preview' | 'import') => {
    if (!qchatPath().trim()) return dashboard.toast('请输入聊天记录源路径', 'warning');
    setBusy(`qchat-${action}`);
    try {
      if (action === 'import' && !await dashboard.confirm({ title: '导入 QQ 聊天记录', message: '消息将写入原始消息队列，重复消息会被跳过。确定继续吗？', tone: 'warning', confirmText: '确认导入' })) return;
      const result = await api.post(`/api/integrations/qq-chat-history/${action}`, {
        source_path: qchatPath().trim(),
        default_group_id: qchatGroup().trim(),
        max_messages: Math.max(1, Number(qchatMax()) || 100000),
        include_training_pairs: trainingPairs(),
      });
      setQchatResult(result);
      const resultData = object(object(result).data ?? result);
      if (action === 'preview') {
        setQchatShadowSender('');
        if (!qchatGroup().trim() && resultData.group_id) setQchatGroup(String(resultData.group_id));
        dashboard.toast('预览完成，请从用户列表中选择影子对象', 'success');
      } else if (qchatShadowSender()) {
        const candidate = qchatSenders().find((item) => String(item.sender_id ?? '') === qchatShadowSender());
        try {
          await api.post('/api/shadow-mode/profiles', {
            source_type: 'imported',
            source_group_id: String(resultData.group_id ?? qchatGroup().trim()),
            target_group_id: qchatGroup().trim() || String(resultData.group_id ?? ''),
            sender_id: qchatShadowSender(),
            activate: true,
          });
          dashboard.toast(`导入完成，已启用 ${String(candidate?.sender_name ?? '所选用户')} 的影子模式`, 'success');
        } catch (caught) {
          dashboard.toast(`聊天记录已导入，但影子学习失败：${caught instanceof Error ? caught.message : '未知错误'}`, 'warning');
        }
      } else dashboard.toast('导入完成', 'success');
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : 'QQ 聊天记录操作失败', 'danger'); }
    finally { setBusy(''); }
  };
  const openIntegration = (item: IntegrationItem) => {
    const dash = object(item.dashboard);
    const url = resolveHostUrl(String(dash.external_url ?? dash.official_page_url ?? dash.url ?? ''));
    const route = String(dash.route ?? '');
    if (route.startsWith('#/')) {
      window.location.hash = route;
      return;
    }
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
  };
  return (
    <div class="page">
      <PageHeader title="功能融合" description="查看配套插件状态，并导入世界书与 QQ 聊天记录。" icon="extension" actions={<Button icon="refresh" onClick={dashboard.loadIntegrations}>刷新状态</Button>} />
      <Panel title="插件面板">
        <div class={styles['integration-grid']}><For each={integrations()}>{(item) => <IntegrationCard item={item} onOpen={() => openIntegration(item)} />}</For></div>
      </Panel>
      <div class={`two-column ${styles['integration-imports']}`}>
        <Panel title="世界书导入" hint="先预览统计，再执行导入">
          <div class={styles['form-stack']}>
            <Input label="目标群组" value={worldbookGroup()} onInput={(event) => setWorldbookGroup(event.currentTarget.value)} />
            <Textarea label="世界书 JSON" rows={12} value={worldbookJson()} onInput={(event) => setWorldbookJson(event.currentTarget.value)} />
            <div class={styles['option-grid']}>
              <label><input type="checkbox" checked={importMemories()} onChange={(event) => setImportMemories(event.currentTarget.checked)} /> 导入记忆/人格候选</label>
              <label><input type="checkbox" checked={importJargons()} onChange={(event) => setImportJargons(event.currentTarget.checked)} /> 导入黑话</label>
              <label><input type="checkbox" checked={importKnowledge()} onChange={(event) => setImportKnowledge(event.currentTarget.checked)} /> 导入知识图谱</label>
              <label><input type="checkbox" checked={includeDisabled()} onChange={(event) => setIncludeDisabled(event.currentTarget.checked)} /> 包含禁用条目</label>
            </div>
            <div class="inline-actions"><Button loading={busy() === 'worldbook-preview'} onClick={() => worldbook('preview')}>预览</Button><Button tone="primary" loading={busy() === 'worldbook-import'} onClick={() => worldbook('import')}>导入</Button></div>
            <Show when={worldbookResult()}><pre class={styles['result-box']}>{summarize(worldbookResult())}</pre></Show>
            <Show when={worldbookHistory().length}>
              <details class="import-history">
                <summary>最近导入记录（{worldbookHistory().length}）</summary>
                <div class="data-list">
                  <For each={worldbookHistory()}>{(item) =>
                    <div class="check-row">
                      <div><strong>{String(item.source_name ?? item.import_id ?? item.id ?? '世界书导入')}</strong><small>{String(item.created_at ?? item.imported_at ?? '')}</small></div>
                      <span>{String(item.status ?? item.success ?? '')}</span>
                    </div>
                  }</For>
                </div>
              </details>
            </Show>
          </div>
        </Panel>
        <Panel title="QQ 聊天记录导入" hint="路径由插件运行环境读取">
          <div class={styles['form-stack']}>
            <Input label="源路径" placeholder="聊天记录文件或目录" value={qchatPath()} onInput={(event) => { setQchatPath(event.currentTarget.value); setQchatResult(null); setQchatShadowSender(''); }} />
            <Input label="群组 ID（可选）" value={qchatGroup()} onInput={(event) => setQchatGroup(event.currentTarget.value)} />
            <Select label="最大消息数" value={qchatMax()} onChange={(event) => setQchatMax(event.currentTarget.value)}>
              <option value="10000">10,000</option><option value="50000">50,000</option><option value="100000">100,000</option><option value="500000">500,000</option>
            </Select>
            <label class={styles['check-option']}><input type="checkbox" checked={trainingPairs()} onChange={(event) => setTrainingPairs(event.currentTarget.checked)} /> 同时生成训练对</label>
            <div class="inline-actions"><Button icon="manage_search" loading={busy() === 'qchat-preview'} onClick={() => qchat('preview')}>解析并列出群友</Button><Button tone="primary" icon={qchatShadowSender() ? 'theater_comedy' : 'upload'} disabled={!qchatResult()} loading={busy() === 'qchat-import'} onClick={() => qchat('import')}>{qchatShadowSender() ? '导入并启用影子' : '导入记录'}</Button></div>
            <Show when={qchatSenders().length}>
              <div class={styles['sender-section']}>
                <div class={styles['sender-heading']}><strong>导入记录中的用户</strong><span>{qchatSenders().length} 人 · 选择一人可在导入后立即启用影子模式</span></div>
                <div class={styles['sender-list']}>
                  <For each={qchatSenders()}>{(sender) => {
                    const senderId = String(sender.sender_id ?? '');
                    const count = Number(sender.message_count) || 0;
                    return <button type="button" disabled={count < 3} classList={{ [styles['sender-row']]: true, [styles['selected']]: qchatShadowSender() === senderId }} onClick={() => setQchatShadowSender(qchatShadowSender() === senderId ? '' : senderId)}>
                      <span class="material-icons">person</span>
                      <span><strong>{String(sender.sender_name ?? senderId)}</strong><small>QQ {String(sender.sender_qq ?? senderId)}</small></span>
                      <b>{count} 条</b>
                      <small>{count >= 3 ? '可学习' : '样本不足'}</small>
                    </button>;
                  }}</For>
                </div>
              </div>
            </Show>
            <Show when={qchatResult()}><pre class={styles['result-box']}>{summarize(qchatResult())}</pre></Show>
          </div>
        </Panel>
      </div>
    </div>
  );
}
