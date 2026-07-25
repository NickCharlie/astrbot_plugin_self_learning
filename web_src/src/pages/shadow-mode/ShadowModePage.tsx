import { createSignal, For, onMount, Show } from 'solid-js';
import { Badge, Button, EmptyState, Input, Panel, SegmentedControl, Select } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatCount, formatTime } from '../../lib/format';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { object } from '../shared';
import styles from './ShadowModePage.module.scss';

type ShadowSource = 'live' | 'imported';
type ShadowGroup = { group_id: string; message_count: number; member_count: number };
type ShadowCandidate = {
  sender_id: string;
  sender_name: string;
  sender_qq: string;
  message_count: number;
  last_timestamp: number;
  ready: boolean;
};
type ShadowProfile = {
  id: number;
  target_group_id: string;
  source_type: ShadowSource;
  source_group_id: string;
  sender_id: string;
  sender_name: string;
  sender_qq: string;
  sample_count: number;
  enabled: boolean;
  updated_at: number;
};

const array = <T,>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];

export function ShadowModePage() {
  const dashboard = useDashboard();
  const [source, setSource] = createSignal<ShadowSource>('live');
  const [groups, setGroups] = createSignal<ShadowGroup[]>([]);
  const [groupId, setGroupId] = createSignal('');
  const [targetGroupId, setTargetGroupId] = createSignal('');
  const [candidates, setCandidates] = createSignal<ShadowCandidate[]>([]);
  const [profiles, setProfiles] = createSignal<ShadowProfile[]>([]);
  const [selectedId, setSelectedId] = createSignal('');
  const [busy, setBusy] = createSignal('');
  const [minimumSamples, setMinimumSamples] = createSignal(3);

  const loadCandidates = async (nextSource = source(), nextGroup = groupId()) => {
    if (!nextGroup) { setCandidates([]); return; }
    setBusy('candidates');
    try {
      const query = new URLSearchParams({ source: nextSource, group_id: nextGroup });
      const response = await api.get<{ data?: unknown }>(`/api/shadow-mode/candidates?${query}`);
      const data = object(response.data ?? response);
      setCandidates(array<ShadowCandidate>(data.candidates));
      setMinimumSamples(Number(data.minimum_samples) || 3);
      setSelectedId('');
    } catch (caught) {
      setCandidates([]);
      dashboard.toast(caught instanceof Error ? caught.message : '读取群友列表失败', 'danger');
    } finally { setBusy(''); }
  };

  const applySource = async (nextSource: ShadowSource, status?: Record<string, unknown>) => {
    setSource(nextSource);
    const sourceMap = object(status?.sources);
    let nextGroups = array<ShadowGroup>(sourceMap[nextSource]);
    if (!status) {
      const response = await api.get<{ data?: unknown }>('/api/shadow-mode');
      const data = object(response.data ?? response);
      nextGroups = array<ShadowGroup>(object(data.sources)[nextSource]);
      setProfiles(array<ShadowProfile>(data.profiles));
    }
    setGroups(nextGroups);
    const nextGroup = nextGroups[0]?.group_id || '';
    setGroupId(nextGroup);
    setTargetGroupId(nextGroup);
    await loadCandidates(nextSource, nextGroup);
  };

  const loadStatus = async () => {
    setBusy('status');
    try {
      const response = await api.get<{ data?: unknown }>('/api/shadow-mode');
      const data = object(response.data ?? response);
      setProfiles(array<ShadowProfile>(data.profiles));
      setMinimumSamples(Number(data.minimum_samples) || 3);
      const sourceMap = object(data.sources);
      const preferred: ShadowSource = array<ShadowGroup>(sourceMap.live).length ? 'live' : 'imported';
      await applySource(preferred, data);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '读取影子模式状态失败', 'danger');
    } finally { setBusy(''); }
  };

  const chooseGroup = async (value: string) => {
    setGroupId(value);
    setTargetGroupId(value);
    await loadCandidates(source(), value);
  };

  const learn = async () => {
    const candidate = candidates().find((item) => item.sender_id === selectedId());
    if (!candidate) return dashboard.toast('请先选择一位可学习的群友', 'warning');
    if (!targetGroupId().trim()) return dashboard.toast('请输入影子模式的生效群组', 'warning');
    setBusy('learn');
    try {
      await api.post('/api/shadow-mode/profiles', {
        source_type: source(),
        source_group_id: groupId(),
        target_group_id: targetGroupId().trim(),
        sender_id: candidate.sender_id,
        activate: true,
      });
      dashboard.toast(`已学习并启用 ${candidate.sender_name} 的影子模式`, 'success');
      await loadStatus();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '影子学习失败', 'danger');
    } finally { setBusy(''); }
  };

  const setEnabled = async (profile: ShadowProfile, enabled: boolean) => {
    setBusy(`profile-${profile.id}`);
    try {
      await api.put(`/api/shadow-mode/profiles/${profile.id}`, { enabled });
      dashboard.toast(enabled ? '影子模式已启用' : '影子模式已停用', 'success');
      await loadStatus();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '更新影子模式失败', 'danger');
    } finally { setBusy(''); }
  };

  onMount(loadStatus);

  return (
    <div class="page">
      <PageHeader title="影子模式" description="从已学习的群聊中选择一位群友，复现其语言节奏与表达习惯。" icon="theater_comedy" actions={<Button icon="refresh" loading={busy() === 'status'} onClick={loadStatus}>刷新</Button>} />

      <Panel title="选择学习对象" hint={`至少需要 ${minimumSamples()} 条有效文本`}>
        <div class={styles['source-toolbar']}>
          <SegmentedControl
            label="聊天记录来源"
            value={source()}
            options={[
              { value: 'live', label: '现有群聊', icon: 'forum' },
              { value: 'imported', label: '导入记录', icon: 'upload_file' },
            ]}
            onChange={(value) => applySource(value)}
          />
          <Select label="来源群组" value={groupId()} disabled={!groups().length} onChange={(event) => chooseGroup(event.currentTarget.value)}>
            <For each={groups()}>{(group) => <option value={group.group_id}>{group.group_id} · {formatCount(group.member_count)} 人</option>}</For>
          </Select>
          <Input label="生效群组" value={targetGroupId()} onInput={(event) => setTargetGroupId(event.currentTarget.value)} />
        </div>

        <Show when={groups().length} fallback={<EmptyState icon="speaker_notes_off" title={source() === 'live' ? '暂无现有群聊记录' : '暂无已导入聊天记录'} />}>
          <div class={styles['candidate-list']} aria-label="可学习群友">
            <For each={candidates()} fallback={<EmptyState icon="group_off" title="这个群组暂无可选用户" />}>{(candidate) =>
              <button
                type="button"
                classList={{ [styles['candidate']]: true, [styles['selected']]: selectedId() === candidate.sender_id }}
                disabled={!candidate.ready}
                aria-pressed={selectedId() === candidate.sender_id}
                onClick={() => setSelectedId(candidate.sender_id)}
              >
                <span class={`${styles['avatar']} material-icons`}>person</span>
                <span class={styles['candidate-copy']}><strong>{candidate.sender_name}</strong><small>QQ {candidate.sender_qq}</small></span>
                <span class={styles['candidate-meta']}><b>{formatCount(candidate.message_count)}</b><small>条消息</small></span>
                <Badge tone={candidate.ready ? 'success' : 'warning'}>{candidate.ready ? '可学习' : '样本不足'}</Badge>
              </button>
            }</For>
          </div>
        </Show>
        <div class={styles['learn-bar']}>
          <span>{selectedId() ? '将重新分析目标用户的全部有效文本，并替换该群组当前影子。' : '选择用户后即可开始学习。'}</span>
          <Button tone="primary" icon="psychology" loading={busy() === 'learn'} disabled={!selectedId()} onClick={learn}>学习并启用</Button>
        </div>
      </Panel>

      <Panel title="影子档案" hint="同一个生效群组同时只启用一份档案">
        <div class={styles['profile-list']}>
          <For each={profiles()} fallback={<EmptyState icon="theater_comedy" title="尚未创建影子档案" />}>{(profile) =>
            <div class={styles['profile-row']}>
              <span class={`${styles['profile-icon']} material-icons`}>{profile.enabled ? 'record_voice_over' : 'voice_over_off'}</span>
              <div><strong>{profile.sender_name}</strong><small>QQ {profile.sender_qq} · {profile.source_type === 'live' ? '现有群聊' : '导入记录'} · {formatCount(profile.sample_count)} 条样本</small></div>
              <div class={styles['profile-scope']}><span>生效群组</span><b>{profile.target_group_id}</b><small>{formatTime(profile.updated_at)}</small></div>
              <Button
                size="sm"
                tone={profile.enabled ? 'warning' : 'success'}
                icon={profile.enabled ? 'pause' : 'play_arrow'}
                loading={busy() === `profile-${profile.id}`}
                onClick={() => setEnabled(profile, !profile.enabled)}
              >{profile.enabled ? '停用' : '启用'}</Button>
            </div>
          }</For>
        </div>
      </Panel>
    </div>
  );
}
