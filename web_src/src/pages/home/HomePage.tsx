import { createMemo, For, Show } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import type { IntegrationItem, PageId, Tone } from '../../types/dashboard';
import { formatCount, formatPercent, safeNumber } from '../../lib/format';
import { list, object, reviews } from '../shared';
import { Badge, Card } from '../../components/ui';
import { PageHeader } from '../../components/layout/PageHeader';
import styles from './HomePage.module.scss';

type EntryStatus = {
  page: PageId;
  title: string;
  description: string;
  icon: string;
  value: string;
  note: string;
  status: string;
  tone: Tone;
};

const modules: Array<{ page: PageId; title: string; description: string; icon: string; tone: string }> = [
  { page: 'jargon-learning', title: '黑话学习', description: '群聊词汇、语义和确认队列', icon: 'forum', tone: 'violet' },
  { page: 'expression-learning', title: '表达方式学习', description: '对话样本、风格特征与学习记录', icon: 'record_voice_over', tone: 'cyan' },
  { page: 'persona-learning', title: '人格学习', description: '当前人格、演化建议与备份', icon: 'person_search', tone: 'amber' },
  { page: 'shadow-mode', title: '影子模式', description: '选择群友并学习其表达习惯', icon: 'theater_comedy', tone: 'cyan' },
];

const quickLinks: Array<{ page: PageId; label: string; icon: string }> = [
  { page: 'jargon-learning', label: '黑话', icon: 'translate' },
  { page: 'expression-learning', label: '表达', icon: 'record_voice_over' },
  { page: 'persona-learning', label: '人格', icon: 'psychology' },
  { page: 'shadow-mode', label: '影子', icon: 'theater_comedy' },
  { page: 'reviews', label: '审查', icon: 'rule' },
  { page: 'content', label: '内容', icon: 'article' },
  { page: 'monitoring', label: '监控', icon: 'monitor_heart' },
];

export function HomePage() {
  const dashboard = useDashboard();
  const snapshot = createMemo(() => {
    const metrics = object(dashboard.data.metrics);
    const health = object(dashboard.data.health);
    const trends = object(dashboard.data.trends);
    const jargon = object(dashboard.data.jargon_stats);
    const statistics = object(object(dashboard.data.data_statistics).data ?? dashboard.data.data_statistics);
    const personaPayload = object(dashboard.data.persona_updates);
    const stylePayload = object(dashboard.data.style_learning_reviews);
    const personaItems = reviews(dashboard.data, 'persona_updates');
    const personaTotal = safeNumber(personaPayload.total, personaItems.length);
    const styleTotal = safeNumber(stylePayload.total, reviews(dashboard.data, 'style_learning_reviews').length);
    const personaIncludesStyle = personaItems.some((item) => item.review_source === 'style_learning');
    const personaPending = personaIncludesStyle ? Math.max(0, personaTotal - styleTotal) : personaTotal;
    const jargonCandidates = safeNumber(jargon.total_candidates ?? object(jargon.data).total_candidates);
    const jargonConfirmed = safeNumber(jargon.confirmed_jargon ?? object(jargon.data).confirmed_jargon);
    const jargonPending = Math.max(0, jargonCandidates - jargonConfirmed);
    const contentCount = safeNumber(statistics.style_learning);
    const graphNodes = safeNumber(statistics.memory) + safeNumber(statistics.knowledge_graph);
    const integrations = list<IntegrationItem>(
      dashboard.integrations()?.dashboards ?? dashboard.integrations(),
    );
    const activeIntegrations = integrations.filter((item) => item.active).length;
    const delegatedIntegrations = integrations.filter((item) => item.delegated).length;
    const reply = integrations.find((item) => item.id === 'group_chat_plus');
    const memory = integrations.find((item) => item.id === 'livingmemory');
    const totalMessages = safeNumber(metrics.total_messages_collected);
    const filtered = safeNumber(metrics.filtered_messages);
    const filterRate = totalMessages ? filtered / totalMessages * 100 : 0;
    const learningEfficiency = safeNumber(metrics.learning_efficiency);
    const backlog = personaPending + styleTotal + jargonPending;
    const batches = list(trends.recent_batches).length;
    const llmSummary = object(metrics.llm_call_summary);
    const llmCalls = safeNumber(llmSummary.total_calls);
    const llmAbnormal = safeNumber(llmSummary.abnormal_provider_count);
    const schemaGroups = dashboard.schema()?.groups || [];
    const editableSettings = schemaGroups.reduce(
      (sum, group) => sum + (group.fields || []).filter((field) => field.editable !== false).length,
      dashboard.schema()?.fields?.filter((field) => field.editable !== false).length || 0,
    );
    const insightTone: Tone = health.overall !== 'healthy' || llmAbnormal > 0
      ? 'danger'
      : backlog > 20 ? 'warning' : 'success';
    return {
      health, totalMessages, filterRate, learningEfficiency, backlog, batches,
      personaPending, styleTotal, jargonCandidates, jargonConfirmed, jargonPending,
      contentCount, graphNodes, integrations, activeIntegrations, delegatedIntegrations,
      reply, memory, llmCalls, llmAbnormal, editableSettings, insightTone,
      backups: list(object(dashboard.data.persona_backups).backups).length,
    };
  });

  const entries = createMemo<EntryStatus[]>(() => {
    const state = snapshot();
    const health = String(state.health.overall || 'unknown');
    return [
      {
        page: 'overview', title: '总览', description: '核心指标与消息趋势', icon: 'dashboard',
        value: formatPercent(state.learningEfficiency), note: `${formatCount(state.totalMessages)} 条消息 · 筛选率 ${formatPercent(state.filterRate)}`,
        status: '数据已同步', tone: state.totalMessages > 0 ? 'success' : 'warning',
      },
      {
        page: 'insights', title: 'AI 巡检', description: '异常、瓶颈与下一步建议', icon: 'auto_awesome',
        value: state.insightTone === 'danger' ? '需关注' : state.insightTone === 'warning' ? '有积压' : '正常',
        note: `${formatCount(state.backlog)} 项待办 · ${formatCount(state.llmAbnormal)} 个模型异常`,
        status: state.insightTone === 'success' ? '暂无高优先级问题' : '建议查看', tone: state.insightTone,
      },
      {
        page: 'monitoring', title: '运行监控', description: '健康状态、热点与模型调用', icon: 'monitor_heart',
        value: health, note: `${formatCount(state.llmCalls)} 次模型调用 · ${formatCount(state.llmAbnormal)} 个异常`,
        status: health === 'healthy' ? '系统健康' : '健康检查异常', tone: health === 'healthy' ? 'success' : 'danger',
      },
      {
        page: 'reviews', title: '审查队列', description: '人格、风格、黑话与批次', icon: 'rate_review',
        value: formatCount(state.backlog), note: `人格 ${formatCount(state.personaPending)} · 风格 ${formatCount(state.styleTotal)} · 黑话 ${formatCount(state.jargonPending)}`,
        status: state.backlog ? '等待处理' : '队列已清空', tone: state.backlog > 20 ? 'warning' : 'success',
      },
      {
        page: 'content', title: '学习内容', description: '对话、分析、表达模式与历史', icon: 'article',
        value: state.contentCount ? formatCount(state.contentCount) : '--', note: '当前表达学习内容总量',
        status: state.contentCount ? '内容可浏览' : '暂无内容', tone: state.contentCount ? 'success' : 'default',
      },
      {
        page: 'reply-strategy', title: '回复策略', description: 'Group Chat Plus 面板', icon: 'forum',
        value: state.reply?.delegated ? 'ON' : state.reply?.active ? '本地' : '--',
        note: state.reply?.delegated ? '回复已委托' : state.reply?.active ? '插件已加载' : '插件未加载',
        status: state.reply?.active ? '可用' : '不可用', tone: state.reply?.active ? 'success' : 'warning',
      },
      {
        page: 'graphs', title: '记忆 / 知识图谱', description: '本地图谱与记忆后端', icon: 'hub',
        value: state.graphNodes ? formatCount(state.graphNodes) : state.memory?.active ? '后端' : '--',
        note: state.graphNodes ? '个当前记忆图谱节点' : state.memory?.delegated ? '读取 LivingMemory 后端' : '本地图谱',
        status: state.graphNodes || state.memory?.active ? '可用' : '暂无节点', tone: state.graphNodes || state.memory?.active ? 'success' : 'default',
      },
      {
        page: 'integrations', title: '功能融合', description: '插件分工、面板和开发 API', icon: 'extension',
        value: state.integrations.length ? `${state.activeIntegrations}/${state.integrations.length}` : '--',
        note: state.delegatedIntegrations ? `${state.delegatedIntegrations} 项已委托` : '插件 API 入口',
        status: state.activeIntegrations ? '已连接' : '仅本插件在线', tone: state.activeIntegrations ? 'success' : 'warning',
      },
      {
        page: 'integrations', title: '世界书 / QQ 导入', description: '预览、导入和结果统计', icon: 'menu_book',
        value: 'API', note: '世界书与聊天记录导入接口',
        status: state.integrations.length ? '可用' : '等待融合状态', tone: state.integrations.length ? 'success' : 'default',
      },
    ];
  });

  return (
    <div class="page">
      <PageHeader home title="学习模块控制台" description="把自主学习链路拆成可观察、可审查、可干预的模块。" icon="psychology" />
      <section class={styles['hero-command']}>
        <div class={styles['hero-command-copy']}>
          <span>LEARNING PULSE</span>
          <h3>学习系统正在持续整理对话经验</h3>
          <p>所有写操作仍由你确认，自动刷新不会打断正在编辑的内容。</p>
          <nav class={styles['quick-dock']} aria-label="学习快捷入口">
            <For each={quickLinks}>{(item) =>
              <a href={`#/${item.page}`} onClick={(event) => { event.preventDefault(); dashboard.navigate(item.page); }}>
                <span class="material-icons">{item.icon}</span>{item.label}
              </a>
            }</For>
          </nav>
        </div>
        <div class={styles['hero-pulse-grid']}>
          <div class={styles['pulse-stat']}><span>学习效率</span><strong>{formatPercent(snapshot().learningEfficiency)}</strong></div>
          <div class={styles['pulse-stat']}><span>待办总量</span><strong>{formatCount(snapshot().backlog)}</strong></div>
          <div class={styles['pulse-stat']}><span>内容样本</span><strong>{snapshot().contentCount ? formatCount(snapshot().contentCount) : '--'}</strong></div>
          <div class={styles['pulse-stat']}><span>最近批次</span><strong>{formatCount(snapshot().batches)}</strong></div>
        </div>
      </section>
      <h3 class="section-label">Independent Learning Modules</h3>
      <div class={styles['learning-module-grid']}>
        <For each={modules}>{(module) =>
          <Card interactive class={`${styles['learning-module-card']} ${styles[module.tone] || ''}`}>
            <a href={`#/${module.page}`} onClick={(event) => { event.preventDefault(); dashboard.navigate(module.page); }}>
              <span class={`${styles['module-icon']} material-icons`}>{module.icon}</span>
              <div>
                <strong>{module.title}</strong><p>{module.description}</p>
                <small>
                  {module.page === 'jargon-learning'
                    ? `候选 ${formatCount(snapshot().jargonCandidates)} · 已确认 ${formatCount(snapshot().jargonConfirmed)}`
                    : module.page === 'expression-learning'
                      ? `内容 ${formatCount(snapshot().contentCount)} · 待审 ${formatCount(snapshot().styleTotal)}`
                      : module.page === 'persona-learning'
                        ? `待审 ${formatCount(snapshot().personaPending)} · 备份 ${formatCount(snapshot().backups)}`
                        : '现有群聊与导入记录均可学习'}
                </small>
              </div>
              <span class="material-icons">arrow_forward</span>
            </a>
          </Card>
        }</For>
      </div>
      <h3 class="section-label">System Entry Points</h3>
      <div class={`${styles['module-grid']} ${styles['system-entry-grid']}`}>
        <For each={entries()}>{(entry) =>
          <Card interactive class={`${styles['route-card']} ${styles['system-entry-card']}`}>
            <a href={`#/${entry.page}`} onClick={(event) => { event.preventDefault(); dashboard.navigate(entry.page); }}>
              <div class={styles['entry-card-head']}>
                <span class="material-icons">{entry.icon}</span>
                <Show when={!dashboard.loading()}>
                  <Badge tone={entry.tone}>{entry.status}</Badge>
                </Show>
              </div>
              <div class={styles['entry-card-copy']}>
                <strong>{entry.title}</strong>
                <p>{entry.description}</p>
              </div>
              <div class={styles['entry-card-state']}>
                <strong>{dashboard.loading() ? "--" : entry.value}</strong>
                <span>{dashboard.loading() ? "加载中..." : entry.note}</span>
              </div>
            </a>
          </Card>
        }</For>
      </div>
    </div>
  );
}
