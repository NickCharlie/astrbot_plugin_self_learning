import { Show, type ParentProps } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { Button, IconButton } from '../ui';
import { formatTime } from '../../lib/format';
import { PageNav } from './PageNav';
import styles from './AppShell.module.scss';

export function AppShell(props: ParentProps) {
  const dashboard = useDashboard();
  return (
    <div class={styles['app-shell']}>
      <header class={styles['topbar']}>
        <a
          class={styles['brand']}
          href="#/home"
          aria-label="返回模块入口"
          onClick={(event) => { event.preventDefault(); dashboard.navigate('home'); }}
        >
          <span class={`${styles['brand-mark']} material-icons`}>psychology</span>
          <h1>
            <div class={styles['eyebrow']}>SELF LEARNING</div>
            <div>监控板</div>
          </h1>
        </a>
        <div class={styles['toolbar']}>
          <span class={styles['update-pill']}>
            <span classList={{ [styles['pulse']]: dashboard.loading() }} />
            <Show when={dashboard.lastUpdated()} fallback="等待首次刷新">
              更新于 {formatTime(dashboard.lastUpdated())}
            </Show>
          </span>
          <Button icon="refresh" loading={dashboard.loading()} onClick={() => dashboard.refresh()}>刷新</Button>
          <IconButton icon={dashboard.theme() === 'dark' ? 'light_mode' : 'dark_mode'} label="切换主题" onClick={dashboard.toggleTheme} />
          <IconButton icon="settings" label="打开设置" tone="primary" onClick={() => dashboard.navigate('settings')} />
        </div>
      </header>
      <PageNav />
      <main class={styles['page-container']}>{props.children}</main>
    </div>
  );
}
