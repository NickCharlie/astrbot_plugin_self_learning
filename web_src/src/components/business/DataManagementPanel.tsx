import { createSignal, For, onMount } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { object } from '../../pages/shared';
import { formatCount, textOrDash } from '../../lib/format';
import { Badge, Button, Panel } from '../ui';
import styles from './DataManagementPanel.module.scss';

// 后端 /api/data/clear/* 已提供按模块清空能力，但 WebUI 一直没有入口，
// 用户只能直接操作数据库。这里补上统计展示与带二次确认的清空操作。
const STAT_ROWS: Array<{ key: string; label: string }> = [
  { key: 'messages', label: '原始/筛选消息' },
  { key: 'persona_reviews', label: '人格学习与审查' },
  { key: 'style_learning', label: '表达风格学习' },
  { key: 'jargon', label: '黑话词库' },
  { key: 'learning_history', label: '学习历史' },
  { key: 'memory', label: '记忆数据' },
  { key: 'knowledge_graph', label: '知识图谱' },
  { key: 'runtime_state', label: '运行时状态' },
];

const CLEAR_ACTIONS: Array<{ key: string; label: string; tone: 'warning' | 'danger' }> = [
  { key: 'messages', label: '消息数据', tone: 'warning' },
  { key: 'persona_reviews', label: '人格学习/审查数据', tone: 'warning' },
  { key: 'style_learning', label: '风格学习数据', tone: 'warning' },
  { key: 'jargon', label: '黑话数据', tone: 'warning' },
  { key: 'learning_history', label: '学习历史数据', tone: 'warning' },
];

export function DataManagementPanel() {
  const dashboard = useDashboard();
  const [stats, setStats] = createSignal<Record<string, unknown>>({});
  const [loading, setLoading] = createSignal(false);
  const [busy, setBusy] = createSignal('');

  const load = async () => {
    setLoading(true);
    try {
      const payload = await api.get<Record<string, unknown>>('/api/data/statistics');
      setStats(object(payload.data ?? payload));
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '数据统计加载失败', 'danger');
    } finally { setLoading(false); }
  };
  onMount(load);

  const clear = async (key: string, label: string, tone: 'warning' | 'danger' = 'danger') => {
    const warning = key === 'all'
      ? '将永久删除插件产生的全部数据（消息、人格审查、风格学习、黑话、学习历史等），且无法恢复。'
      : `将永久删除「${label}」相关数据，且无法恢复。`;
    if (!await dashboard.confirm({ title: key === 'all' ? '清空全部数据' : `清空${label}`, message: warning, tone, confirmText: '确认清空' })) return;
    setBusy(key);
    try {
      const result = await api.delete<{ message?: string; deleted?: number }>(`/api/data/clear/${key}`);
      const deleted = result.deleted === undefined ? '' : `（${formatCount(result.deleted)} 行）`;
      dashboard.toast(`${result.message || `已清空${label}`}${deleted}`, 'success');
      await load();
      await dashboard.refresh(true);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '清空数据失败', 'danger');
    } finally { setBusy(''); }
  };

  return (
    <Panel
      title="数据管理"
      hint="按模块查看数据量，并在二次确认后清空；清空操作不可撤销"
      icon="storage"
      actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新统计</Button>}
    >
      <div class={styles['stat-grid']}>
        <For each={STAT_ROWS}>{(row) =>
          <div class={styles['stat-card']}>
            <span>{row.label}</span>
            <strong>{textOrDash(stats()[row.key])}</strong>
          </div>
        }</For>
      </div>
      <div class={styles['action-block']}>
        <div class={styles['action-head']}>
          <strong>按模块清空</strong>
          <Badge tone="warning">不可恢复</Badge>
        </div>
        <div class="inline-actions">
          <For each={CLEAR_ACTIONS}>{(action) =>
            <Button size="sm" tone={action.tone} loading={busy() === action.key} onClick={() => clear(action.key, action.label, action.tone)}>
              清空{action.label}
            </Button>
          }</For>
          <Button size="sm" tone="danger" loading={busy() === 'all'} onClick={() => clear('all', '全部数据', 'danger')}>清空全部数据</Button>
        </div>
      </div>
    </Panel>
  );
}
