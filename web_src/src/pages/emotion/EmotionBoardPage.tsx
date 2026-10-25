import { createMemo, createSignal, For, onMount, Show } from 'solid-js';
import type { EChartsOption } from 'echarts';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { Tone } from '../../types/dashboard';
import { formatCount, formatPercent, formatTime, safeNumber, textOrDash } from '../../lib/format';
import { EChart } from '../../components/charts/EChart';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge, Button, EmptyState, Input, Panel, ProgressBar, Select, StatCard, Textarea } from '../../components/ui';
import styles from './EmotionBoardPage.module.scss';

type MoodRow = { group_id: string; mood_type: string; intensity: number; description: string; timestamp: number; start_time: number };
type AffectionEntry = { user_id: string; group_id: string; level: number };
type GroupSummary = { group_id: string; total_users: number; average: number; high: number; low: number };
type GateDaily = { stat_date: string; accepted: number; skipped: number; avg_score: number; accept_rate: number | null };
type GateTelemetry = {
  enabled: boolean; threshold: number;
  weights: Record<string, number>;
  recent: Array<{ timestamp: number; group_id: string; score: number; decision: boolean }>;
  counters: { accepted: number; skipped: number };
  recent_factor_avg: Record<string, number>;
};
type ForgetCandidate = { id: number; kind: string; group_id: string; title: string; detail: string; stage: number; last_used: number; created: number };
type Board = {
  available: boolean;
  moods: { active: MoodRow[]; history: MoodRow[] };
  affection: { groups: GroupSummary[]; leaderboard: AffectionEntry[]; bottom: AffectionEntry[]; overall?: { total_users: number; average: number } };
  emotion_profiles: { total: number; dominant_distribution: Array<{ emotion: string; count: number }> };
  gate: { daily: GateDaily[]; telemetry: GateTelemetry | null };
  forgetting: {
    enabled: boolean; running: boolean; last_run_at: number | null;
    config: Record<string, number | boolean>;
    stage_labels: Record<string, string>;
    distribution: Record<string, Record<string, number>>;
    candidates: { expression: ForgetCandidate[]; jargon: ForgetCandidate[] };
    last_report: Record<string, any> | null;
  } | null;
};
type Trends = {
  days: number;
  affection_delta: Array<{ date: string; delta: number }>;
  mood_changes: Array<{ date: string; count: number }>;
  gate: GateDaily[];
};

const MOOD_OPTIONS = ['happy', 'excited', 'playful', 'calm', 'curious', 'nostalgic', 'serious', 'anxious', 'sad', 'angry'];
const MOOD_LABELS: Record<string, string> = {
  happy: '开心', excited: '兴奋', playful: '顽皮', calm: '平静', curious: '好奇',
  nostalgic: '怀旧', serious: '严肃', anxious: '焦虑', sad: '低落', angry: '生气',
};
const FACTOR_LABELS: Record<string, string> = { affection: '好感度', sentiment: '消息情感', mood: 'Bot 心情', stability: '情绪稳定性' };
const KIND_LABELS: Record<string, string> = { expression: '表达', jargon: '黑话' };

const moodTone = (type: string): Tone =>
  ['happy', 'excited', 'playful'].includes(type) ? 'success'
    : ['sad', 'anxious', 'angry'].includes(type) ? 'danger' : 'default';

export function EmotionBoardPage() {
  const dashboard = useDashboard();
  const [board, setBoard] = createSignal<Board | null>(null);
  const [trends, setTrends] = createSignal<Trends | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [busy, setBusy] = createSignal('');
  const [moodGroup, setMoodGroup] = createSignal('');
  const [moodType, setMoodType] = createSignal('happy');
  const [moodIntensity, setMoodIntensity] = createSignal('0.6');
  const [moodDescription, setMoodDescription] = createSignal('');

  const load = async () => {
    setLoading(true);
    try {
      const [boardPayload, trendsPayload] = await Promise.all([
        api.get<{ data?: Board }>('/api/emotion/board'),
        api.get<{ data?: Trends }>('/api/emotion/trends?days=14'),
      ]);
      setBoard((boardPayload.data ?? boardPayload) as Board);
      setTrends((trendsPayload.data ?? trendsPayload) as Trends);
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '情绪板块加载失败', 'danger');
    } finally { setLoading(false); }
  };
  // 页面挂载即加载
  onMount(load);

  const forgetting = () => board()?.forgetting ?? null;
  const candidates = () => {
    const data = forgetting()?.candidates;
    if (!data) return [] as ForgetCandidate[];
    return [...(data.expression || []), ...(data.jargon || [])]
      .sort((a, b) => b.stage - a.stage || (a.last_used || 0) - (b.last_used || 0));
  };
  const stageCounts = (kind: string) => forgetting()?.distribution?.[kind] ?? {};
  const gateToday = createMemo(() => {
    const daily = trends()?.gate ?? [];
    return daily.length ? daily[daily.length - 1] : null;
  });

  const trendOption = createMemo<EChartsOption>(() => {
    const delta = trends()?.affection_delta ?? [];
    const moodChanges = trends()?.mood_changes ?? [];
    const byDate = new Map(moodChanges.map((item) => [item.date, item.count]));
    const labels = delta.map((item) => item.date);
    for (const date of byDate.keys()) if (!labels.includes(date)) labels.push(date);
    labels.sort();
    const deltaMap = new Map(delta.map((item) => [item.date, item.delta]));
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 46, right: 24, top: 28, bottom: 34 },
      xAxis: { type: 'category', data: labels },
      yAxis: { type: 'value' },
      series: [
        { name: '好感度净变化', type: 'bar', data: labels.map((label) => deltaMap.get(label) ?? 0), itemStyle: { color: '#6476ff' } },
        { name: '心情切换次数', type: 'line', smooth: true, data: labels.map((label) => byDate.get(label) ?? 0), lineStyle: { color: '#17b6a4' } },
      ],
    };
  });
  const gateOption = createMemo<EChartsOption>(() => {
    const gate = trends()?.gate ?? [];
    const labels = gate.map((item) => item.stat_date);
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 46, right: 24, top: 28, bottom: 34 },
      xAxis: { type: 'category', data: labels },
      yAxis: { type: 'value', max: 1 },
      series: [
        { name: '学习放行率', type: 'line', smooth: true, data: gate.map((item) => item.accept_rate ?? null), lineStyle: { color: '#f59e0b' } },
        { name: '平均加权分', type: 'line', smooth: true, data: gate.map((item) => item.avg_score), lineStyle: { color: '#6476ff' } },
      ],
    };
  });

  const runAction = async (body: Record<string, unknown>, label: string) => {
    setBusy(label);
    try {
      const result = await api.post<{ success?: boolean; message?: string }>('/api/emotion/action', body);
      dashboard.toast(result.message || '操作已完成', result.success === false ? 'danger' : 'success');
      await load();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '操作失败', 'danger');
    } finally { setBusy(''); }
  };

  const submitMood = () => runAction({
    action: 'set_mood',
    group_id: moodGroup().trim(),
    mood_type: moodType(),
    intensity: Number(moodIntensity()) || 0.6,
    description: moodDescription().trim(),
  }, 'set-mood');

  const activeGroups = () => (board()?.moods.active ?? []).map((mood) => mood.group_id);

  return (
    <div class="page">
      <PageHeader
        title="情绪中枢"
        description="Bot 心情、好感度与学习联动的状态面板：走向分析、加权闸门与三阶段遗忘治理。"
        icon="psychology"
        actions={<Button icon="refresh" loading={loading()} onClick={load}>刷新</Button>}
      />

      <div class="metrics-grid">
        <StatCard
          label="当前心情"
          icon="mood"
          value={board()?.moods.active?.[0] ? (MOOD_LABELS[board()!.moods.active[0].mood_type] ?? board()!.moods.active[0].mood_type) : '--'}
          note={board()?.moods.active?.length ? `${board()!.moods.active.length} 个群组有活跃心情` : '暂无活跃心情'}
          tone={board()?.moods.active?.[0] ? moodTone(board()!.moods.active[0].mood_type) : 'default'}
        />
        <StatCard label="平均好感度" icon="favorite" value={formatCount(board()?.affection?.overall?.average ?? 0)} note={`${formatCount(board()?.affection?.overall?.total_users ?? 0)} 位用户`} />
        <StatCard
          label="闸门放行率" icon="gate"
          value={gateToday()?.accept_rate != null ? formatPercent(gateToday()!.accept_rate) : '--'}
          note={board()?.gate?.telemetry?.enabled ? `阈值 ${board()!.gate!.telemetry!.threshold}` : '闸门未启用'}
          tone={board()?.gate?.telemetry?.enabled ? 'success' : 'warning'}
        />
        <StatCard
          label="遗忘候选" icon="delete_sweep"
          value={formatCount(candidates().length)}
          note={forgetting()?.enabled ? `周期 ${forgetting()!.config.cycle_days} 天` : '遗忘未启用'}
          tone={candidates().length ? 'warning' : 'default'}
        />
      </div>

      <div class="two-column">
        <Panel title="Bot 心情状态" hint="各群组当前活跃心情">
          <Show when={(board()?.moods.active ?? []).length} fallback={<EmptyState title="暂无活跃心情" detail="可在下方手动设置，或等待每日情绪更新。" />}>
            <div class="data-list">
              <For each={board()?.moods.active ?? []}>{(mood) =>
                <div class="check-row">
                  <div>
                    <strong>{textOrDash(mood.group_id)}</strong>
                    <small>{textOrDash(mood.description)} · {formatTime(mood.timestamp)}</small>
                  </div>
                  <div class={styles['mood-right']}>
                    <Badge tone={moodTone(mood.mood_type)}>{MOOD_LABELS[mood.mood_type] ?? mood.mood_type}</Badge>
                    <ProgressBar label={`强度 ${formatPercent(mood.intensity)}`} value={safeNumber(mood.intensity) * 100} />
                  </div>
                </div>
              }</For>
            </div>
          </Show>
          <div class={styles['mood-form']}>
            <Input label="群组 ID" value={moodGroup()} onInput={(event) => setMoodGroup(event.currentTarget.value)} />
            <Select label="心情" value={moodType()} onChange={(event) => setMoodType(event.currentTarget.value)}>
              <For each={MOOD_OPTIONS}>{(option) => <option value={option}>{MOOD_LABELS[option]}</option>}</For>
            </Select>
            <Select label="强度" value={moodIntensity()} onChange={(event) => setMoodIntensity(event.currentTarget.value)}>
              <option value="0.2">低</option><option value="0.6">中</option><option value="1.0">高</option>
            </Select>
            <Textarea label="描述（可选）" rows={2} value={moodDescription()} onInput={(event) => setMoodDescription(event.currentTarget.value)} />
            <div class="inline-actions">
              <Button
                tone="primary" icon="edit" loading={busy() === 'set-mood'} disabled={!moodGroup().trim()}
                onClick={submitMood}
              >设置心情</Button>
              <Show when={activeGroups().length && !moodGroup().trim()}>
                <Button size="sm" onClick={() => setMoodGroup(activeGroups()[0])}>填入首个群组</Button>
              </Show>
            </div>
          </div>
        </Panel>

        <Panel title="好感度概览" hint="全群好感分布与排行榜">
          <Show when={board()?.affection} fallback={<EmptyState title="暂无好感度数据" />}>
            <div class="data-list">
              <For each={board()?.affection.groups ?? []}>{(group) =>
                <div class="check-row">
                  <div><strong>{textOrDash(group.group_id)}</strong><small>{formatCount(group.total_users)} 位用户 · 高好感 {formatCount(group.high)} · 低好感 {formatCount(group.low)}</small></div>
                  <Badge tone={group.average >= 20 ? 'success' : group.average <= -20 ? 'danger' : 'default'}>{formatCount(group.average)}</Badge>
                </div>
              }</For>
            </div>
            <div class={styles['rank-grid']}>
              <div>
                <h4>好感 TOP</h4>
                <For each={board()?.affection.leaderboard ?? []}>{(entry) =>
                  <div class={styles['rank-row']}><span>{entry.user_id}</span><b>+{formatCount(entry.level)}</b></div>
                }</For>
              </div>
              <div>
                <h4>好感 BOTTOM</h4>
                <For each={board()?.affection.bottom ?? []}>{(entry) =>
                  <div class={styles['rank-row']}><span>{entry.user_id}</span><b>{formatCount(entry.level)}</b></div>
                }</For>
              </div>
            </div>
          </Show>
        </Panel>
      </div>

      <Panel title="走向分析" hint="近 14 天好感度净变化、心情波动与闸门放行走势">
        <div class="two-column">
          <EChart option={trendOption()} class="chart-lg" />
          <EChart option={gateOption()} class="chart-lg" />
        </div>
        <Show when={(board()?.emotion_profiles.dominant_distribution ?? []).length}>
          <h4 class={styles['dist-title']}>用户主导情绪分布</h4>
          <div class={styles['dist-row']}>
            <For each={board()?.emotion_profiles.dominant_distribution ?? []}>{(item) =>
              <span class={styles['dist-chip']}><b>{item.emotion}</b>{formatCount(item.count)}</span>
            }</For>
          </div>
        </Show>
      </Panel>

      <Panel title="学习联动 · 情绪加权闸门" hint="好感度 35% + 消息情感 25% + Bot 心情 20% + 情绪稳定性 20%">
        <Show
          when={board()?.gate.telemetry}
          fallback={<EmptyState title="闸门遥测不可用" detail="插件运行中才会产生判定记录；历史统计见上方走向分析。" />}
        >
          {(() => {
            const telemetry = board()!.gate.telemetry!;
            const accepted = safeNumber(telemetry.counters?.accepted);
            const skipped = safeNumber(telemetry.counters?.skipped);
            const total = accepted + skipped;
            return (
              <div class={styles['gate-grid']}>
                <div>
                  <div class="check-row">
                    <div><strong>累计放行</strong><small>重启后计数归零，长期趋势看日统计</small></div>
                    <Badge tone="success">{formatCount(accepted)}</Badge>
                  </div>
                  <div class="check-row">
                    <div><strong>累计拦截</strong><small>原始消息仍会采集，仅跳过学习</small></div>
                    <Badge tone="warning">{formatCount(skipped)}</Badge>
                  </div>
                  <div class="check-row">
                    <div><strong>放行占比</strong><small>本次运行以来</small></div>
                    <Badge tone={total && skipped / total > 0.5 ? 'danger' : 'default'}>{total ? formatPercent(accepted / total) : '--'}</Badge>
                  </div>
                </div>
                <div>
                  <h4 class={styles['dist-title']}>近期因子均值</h4>
                  <For each={Object.keys(telemetry.recent_factor_avg ?? {})}>{(key) =>
                    <ProgressBar label={`${FACTOR_LABELS[key] ?? key}（权重 ${formatPercent(telemetry.weights?.[key] ?? 0)}）`} value={safeNumber(telemetry.recent_factor_avg[key]) * 100} />
                  }</For>
                </div>
                <div>
                  <h4 class={styles['dist-title']}>近期判定</h4>
                  <For each={(telemetry.recent ?? []).slice(-10).reverse()}>{(item) =>
                    <div class={styles['rank-row']}>
                      <span>{item.group_id}</span>
                      <small>{formatTime(item.timestamp)}</small>
                      <b>{formatCount(item.score)}</b>
                      <Badge tone={item.decision ? 'success' : 'warning'}>{item.decision ? '放行' : '拦截'}</Badge>
                    </div>
                  }</For>
                </div>
              </div>
            );
          })()}
        </Show>
      </Panel>

      <Panel
        title="三阶段遗忘治理"
        hint="连续三个周期无使用/正向反馈即删除；负反馈或手动标记反感直接进入二期"
        actions={
          <div class="inline-actions">
            <Button icon="run_circle" loading={busy() === 'run-cycle'} onClick={() => runAction({ action: 'run_forgetting_cycle' }, 'run-cycle')}>立即执行周期</Button>
          </div>
        }
      >
        <Show when={forgetting()} fallback={<EmptyState title="遗忘管理器未运行" detail="需要插件完整启动且数据库可用。" />}>
          <div class={styles['forget-grid']}>
            <For each={['expression', 'jargon']}>{(kind) =>
              <div>
                <h4>{KIND_LABELS[kind]}阶段分布</h4>
                <div class={styles['dist-row']}>
                  <For each={['0', '1', '2', '3']}>{(stage) =>
                    <span class={styles['dist-chip']}>
                      <b>{forgetting()!.stage_labels?.[stage] ?? `阶段 ${stage}`}</b>
                      {formatCount(stageCounts(kind)[stage])}
                    </span>
                  }</For>
                </div>
                <small class={styles['forget-meta']}>
                  上次执行：{forgetting()!.last_run_at ? formatTime(forgetting()!.last_run_at) : '尚未执行'} ·
                  周期 {formatCount(forgetting()!.config.cycle_days)} 天 · 宽限 {formatCount(forgetting()!.config.grace_days)} 天
                </small>
              </div>
            }</For>
          </div>
          <Show when={candidates().length} fallback={<EmptyState title="暂无遗忘候选" detail="所有条目都处于新鲜阶段。" />}>
            <div class="data-list">
              <For each={candidates()}>{(item) =>
                <div class="check-row">
                  <div>
                    <strong>{textOrDash(item.title)}</strong>
                    <small>{KIND_LABELS[item.kind] ?? item.kind} · {textOrDash(item.group_id)} · 最后使用 {item.last_used ? formatTime(item.last_used) : '从未'}</small>
                  </div>
                  <Badge tone={item.stage >= 3 ? 'danger' : item.stage === 2 ? 'warning' : 'default'}>
                    {forgetting()!.stage_labels?.[String(item.stage)] ?? `阶段 ${item.stage}`}
                  </Badge>
                  <div class="inline-actions">
                    <Button size="sm" onClick={() => runAction({ action: 'reset_stage', kind: item.kind, id: item.id }, `reset-${item.id}`)}>重置</Button>
                    <Button size="sm" tone="warning" onClick={() => runAction({ action: 'mark_dislike', kind: item.kind, id: item.id }, `dislike-${item.id}`)}>标记反感</Button>
                    <Button size="sm" tone="danger" onClick={() => runAction({ action: 'delete_item', kind: item.kind, id: item.id }, `delete-${item.id}`)}>删除</Button>
                  </div>
                </div>
              }</For>
            </div>
          </Show>
        </Show>
      </Panel>
    </div>
  );
}

// 供测试引用的纯展示辅助
export const EMOTION_CONSTANTS = { MOOD_LABELS, FACTOR_LABELS, KIND_LABELS, FACTOR_WEIGHT_COUNT: 4 };
export const emotionListTotal = (
  forgetting: { candidates: { expression: unknown[]; jargon: unknown[] } } | null | undefined,
): number =>
  (forgetting?.candidates?.expression?.length ?? 0) + (forgetting?.candidates?.jargon?.length ?? 0);
