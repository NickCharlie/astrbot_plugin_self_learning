import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { GraphPayload } from '../../types/dashboard';
import { object } from '../shared';
import { formatCount } from '../../lib/format';
import { socialGroupId, socialGroupName, socialToGraph, type SocialGroup } from '../../lib/socialGraph';
import { GraphView } from '../../components/business/GraphView';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, EmptyState, Input, Panel, SegmentedControl, Select } from '../../components/ui';
import styles from './GraphsPage.module.scss';

type GraphType = 'memory' | 'knowledge' | 'social';
type Layout = 'force' | 'circular';


export function GraphsPage() {
  const dashboard = useDashboard();
  const [type, setType] = createSignal<GraphType>('memory');
  const [layout, setLayout] = createSignal<Layout>('force');
  const [groupId, setGroupId] = createSignal('');
  const [payload, setPayload] = createSignal<GraphPayload>({});
  const [loading, setLoading] = createSignal(false);
  const [busy, setBusy] = createSignal('');
  const [groups, setGroups] = createSignal<SocialGroup[]>([]);
  const [socialGroup, setSocialGroup] = createSignal('');
  const [socialInfo, setSocialInfo] = createSignal<Record<string, unknown>>({});
  // 共享递增令牌：快速切换视图/群组时旧响应不得覆盖新数据（Sourcery review）
  let requestToken = 0;

  const loadSocial = async (targetGroupId: string) => {
    const token = ++requestToken;
    if (!targetGroupId) {
      setPayload({});
      setSocialInfo({});
      return;
    }
    setLoading(true);
    try {
      const data = await api.get<Record<string, unknown>>(`/api/social_relations/${encodeURIComponent(targetGroupId)}`);
      if (token !== requestToken) return;
      setSocialInfo(data);
      setPayload(socialToGraph(data));
      if (data.success === false && data.error) dashboard.toast(String(data.error), 'warning');
    } catch (caught) {
      if (token === requestToken) dashboard.toast(caught instanceof Error ? caught.message : '社交关系加载失败', 'danger');
    } finally { if (token === requestToken) setLoading(false); }
  };

  const load = async () => {
    if (type() === 'social') return loadSocial(socialGroup());
    const token = ++requestToken;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (groupId().trim()) params.set('group_id', groupId().trim());
      const data = await api.get<GraphPayload>(`/api/graphs/${type()}?${params}`);
      if (token !== requestToken) return;
      setPayload(data);
    } catch (caught) {
      if (token === requestToken) dashboard.toast(caught instanceof Error ? caught.message : '图谱加载失败', 'danger');
    } finally { if (token === requestToken) setLoading(false); }
  };
  onMount(load);
  onMount(async () => {
    try {
      const result = await api.get<{ groups?: SocialGroup[] }>('/api/social_relations/groups');
      const rows = Array.isArray(result.groups) ? result.groups : [];
      setGroups(rows);
      // 等 For 渲染完 option 后再写入 value，避免 select 回退到第一项；
      // 若用户已切到社交视图，选中后立即加载关系，避免出现空白图。
      if (rows.length) queueMicrotask(() => {
        const first = socialGroupId(rows[0]);
        setSocialGroup(first);
        if (type() === 'social') void loadSocial(first);
      });
    } catch { /* 群组列表加载失败不阻塞图谱页 */ }
  });

  const socialAction = async (action: 'analyze' | 'clear' | 'share') => {
    const targetGroupId = socialGroup();
    if (!targetGroupId) return dashboard.toast('请先选择群组', 'warning');
    if (action === 'analyze' && !await dashboard.confirm({
      title: '重新分析社交关系',
      message: '将调用 LLM 分析该群组的成员互动关系，可能需要一段时间。确定继续吗？',
      tone: 'warning',
      confirmText: '开始分析',
    })) return;
    if (action === 'clear' && !await dashboard.confirm({
      title: '清空社交关系',
      message: '将删除该群组已分析的社交关系数据，确定继续吗？',
      tone: 'danger',
      confirmText: '确认清空',
    })) return;
    setBusy(action);
    try {
      if (action === 'analyze') {
        const result = await api.post<{ success?: boolean; message?: string }>(`/api/social_relations/${encodeURIComponent(targetGroupId)}/analyze`, {});
        dashboard.toast(result.message || '社交关系分析已完成', result.success === false ? 'warning' : 'success');
        await loadSocial(targetGroupId);
      } else if (action === 'clear') {
        await api.delete(`/api/social_relations/${encodeURIComponent(targetGroupId)}/clear`);
        dashboard.toast('社交关系数据已清空', 'success');
        await loadSocial(targetGroupId);
      } else {
        const result = await api.post<{ data?: { share_url?: string } }>(`/api/social_relations/${encodeURIComponent(targetGroupId)}/share`, { expires_hours: 168 });
        const shareUrl = result.data?.share_url;
        if (!shareUrl) {
          dashboard.toast('分享链接已创建', 'success');
        } else if (navigator.clipboard?.writeText) {
          try {
            await navigator.clipboard.writeText(shareUrl);
            dashboard.toast('分享链接已复制到剪贴板', 'success');
          } catch {
            // 剪贴板被拒绝时仍要把已创建的链接展示给用户（Sourcery review）
            dashboard.toast(`分享链接已创建：${shareUrl}`, 'warning');
          }
        } else {
          dashboard.toast(`分享链接：${shareUrl}`, 'success');
        }
      }
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '社交关系操作失败', 'danger');
    } finally { setBusy(''); }
  };

  const hasNodes = () => Array.isArray(object(payload()).nodes) && (object(payload()).nodes as unknown[]).length > 0;
  return (
    <div class="page">
      <PageHeader title="记忆 / 知识图谱" description="探索记忆节点、知识实体、群友社交关系及其联系；拖动位置会在本次会话中保留。" icon="hub" />
      <Panel
        title="图谱视图"
        hint="稳定静态布局避免每次刷新后节点重新飞散"
        actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>}
      >
        <div class={styles['graph-toolbar']}>
          <SegmentedControl
            value={type()}
            onChange={(next) => { setType(next); queueMicrotask(() => next === 'social' ? loadSocial(socialGroup()) : load()); }}
            options={[
              { value: 'memory', label: '记忆图谱' },
              { value: 'knowledge', label: '知识图谱' },
              { value: 'social', label: '社交关系' },
            ]}
          />
          <SegmentedControl value={layout()} onChange={setLayout} options={[{ value: 'force', label: '稳定布局' }, { value: 'circular', label: '环形布局' }]} />
          <Show
            when={type() === 'social'}
            fallback={<Input placeholder="群组 ID（可选）" value={groupId()} onInput={(event) => setGroupId(event.currentTarget.value)} onKeyDown={(event) => event.key === 'Enter' && load()} />}
          >
            <Select
              label="群组"
              value={socialGroup()}
              onChange={(event) => { const next = event.currentTarget.value; setSocialGroup(next); queueMicrotask(() => loadSocial(next)); }}
            >
              <option value="">选择群组</option>
              <For each={groups()}>{(group) => <option value={socialGroupId(group)}>{socialGroupName(group)}</option>}</For>
            </Select>
          </Show>
        </div>
        <Show when={type() === 'social' && socialGroup()}>
          <div class="inline-actions">
            <Button size="sm" icon="auto_awesome" disabled={Boolean(busy())} loading={busy() === 'analyze'} onClick={() => socialAction('analyze')}>重新分析</Button>
            <Button size="sm" icon="share" disabled={Boolean(busy())} loading={busy() === 'share'} onClick={() => socialAction('share')}>分享图谱</Button>
            <Button size="sm" tone="danger" icon="delete" disabled={Boolean(busy())} loading={busy() === 'clear'} onClick={() => socialAction('clear')}>清空关系</Button>
          </div>
          <p class="footer-note">
            成员 {formatCount(socialInfo().member_count)} · 关系 {formatCount(socialInfo().relation_count)} · 消息 {formatCount(socialInfo().message_count)}
          </p>
        </Show>
        <Show when={hasNodes()} fallback={<EmptyState title={type() === 'social' ? '该群组暂无社交关系' : '图谱暂无节点'} detail={type() === 'social' ? '点击「重新分析」基于群聊记录生成关系图。' : '可尝试清空群组筛选后刷新。'} />}>
          <GraphView payload={payload()} layout={layout()} />
        </Show>
      </Panel>
    </div>
  );
}
