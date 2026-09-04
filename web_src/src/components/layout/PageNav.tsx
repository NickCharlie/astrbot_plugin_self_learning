import { For } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import type { PageId } from '../../types/dashboard';
import styles from './PageNav.module.scss';

const items: Array<{ id: PageId; label: string; icon: string; accent: string }> = [
  { id: 'home', label: '模块入口', icon: 'home', accent: 'home' },
  { id: 'overview', label: '总览', icon: 'dashboard', accent: 'overview' },
  { id: 'insights', label: 'AI 巡检', icon: 'auto_awesome', accent: 'insights' },
  { id: 'monitoring', label: '运行监控', icon: 'monitor_heart', accent: 'monitoring' },
  { id: 'reviews', label: '审查队列', icon: 'fact_check', accent: 'reviews' },
  { id: 'jargon-learning', label: '黑话学习', icon: 'forum', accent: 'jargon-learning' },
  { id: 'expression-learning', label: '表达学习', icon: 'record_voice_over', accent: 'expression-learning' },
  { id: 'persona-learning', label: '人格学习', icon: 'person_search', accent: 'persona-learning' },
  { id: 'shadow-mode', label: '影子模式', icon: 'theater_comedy', accent: 'shadow-mode' },
  { id: 'content', label: '学习内容', icon: 'library_books', accent: 'content' },
  { id: 'graphs', label: '图谱', icon: 'hub', accent: 'graphs' },
  { id: 'reply-strategy', label: '回复策略', icon: 'quickreply', accent: 'reply-strategy' },
  { id: 'integrations', label: '功能融合', icon: 'extension', accent: 'integrations' },
  { id: 'settings', label: '设置', icon: 'tune', accent: 'settings' },
];

export function PageNav() {
  const dashboard = useDashboard();
  return (
    <nav class={styles['page-nav']} aria-label="Dashboard 页面">
      <For each={items}>{(item) =>
        <a
          href={`#/${item.id}`}
          data-accent={item.accent}
          classList={{ [styles['active']]: dashboard.page() === item.id }}
          onClick={(event) => { event.preventDefault(); dashboard.navigate(item.id); }}
        >
          <span class="material-icons">{item.icon}</span><span>{item.label}</span>
        </a>
      }</For>
    </nav>
  );
}
