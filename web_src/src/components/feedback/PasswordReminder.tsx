import { Show, createSignal, onMount } from 'solid-js';
import { api } from '../../services/api';
import styles from './PasswordReminder.module.scss';

const DISMISS_KEY = 'selflearning.password-reminder.dismissed';

/**
 * 免密模式提醒：WebUI 密码未启用时展示一次，用户关闭后不再打扰。
 * 仅在后端显式返回 password_enabled === false 时出现，兼容旧后端与状态查询失败的场景。
 */
export function PasswordReminderBanner() {
  const [visible, setVisible] = createSignal(false);

  onMount(async () => {
    if (localStorage.getItem(DISMISS_KEY) === '1') return;
    try {
      const status = await api.get<{ password_enabled?: boolean }>('/api/password_status');
      if (status.password_enabled === false) setVisible(true);
    } catch {
      // 状态查询失败时不打扰用户
    }
  });

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, '1');
    setVisible(false);
  };

  return (
    <Show when={visible()}>
      <div class={styles['reminder']} role="status">
        <span class="material-icons" aria-hidden="true">lock_open</span>
        <p>当前 WebUI 处于免密模式，建议在插件配置中启用 WebUI 密码以保护管理面板。</p>
        <button type="button" class={styles['dismiss']} onClick={dismiss}>知道了</button>
      </div>
    </Show>
  );
}
