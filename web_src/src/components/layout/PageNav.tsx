import { For } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import type { PageId } from '../../types/dashboard';
import styles from './PageNav.module.scss';

const items: Array<{ id: PageId; label: string; icon: string }> = [
  { id: 'home', label: '模块入口', icon: 'home' },
  { id: 'overview', label: '总览', icon: 'dashboard' },
  { id: 'insights', label: 'AI 巡检', icon: 'auto_awesome' },
  { id: 'monitoring', label: '运行监控', icon: 'monitor_heart' },
  { id: 'reviews', label: '审查队列', icon: 'fact_check' },
  { id: 'jargon-learning', label: '黑话学习', icon: 'forum' },
  { id: 'expression-learning', label: '表达学习', icon: 'record_voice_over' },
  { id: 'persona-learning', label: '人格学习', icon: 'person_search' },
  { id: 'shadow-mode', label: '影子模式', icon: 'theater_comedy' },
  { id: 'content', label: '学习内容', icon: 'library_books' },
  { id: 'graphs', label: '图谱', icon: 'hub' },
  { id: 'reply-strategy', label: '回复策略', icon: 'quickreply' },
  { id: 'integrations', label: '功能融合', icon: 'extension' },
  { id: 'settings', label: '设置', icon: 'tune' },
];

export function PageNav() {
  const dashboard = useDashboard();
  return (
    <nav class={styles['page-nav']} aria-label="Dashboard 页面">
      <For each={items}>{(item) =>
        <a
          href={`#/${item.id}`}
          classList={{ [styles['active']]: dashboard.page() === item.id }}
          onClick={(event) => { event.preventDefault(); dashboard.navigate(item.id); }}
        >
          <span class="material-icons">{item.icon}</span><span>{item.label}</span>
        </a>
      }</For>
    </nav>
  );
}
