import { Show, createSignal, onMount } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { replaceLocation } from '../../lib/navigation';
import { Badge, Button, Input } from '../ui';
import styles from './WebuiPasswordPanel.module.scss';

const MIN_PASSWORD_LENGTH = 8;
const REDIRECT_DELAY_MS = 900;

/**
 * WebUI 访问密码面板：免密模式下设置自定义密码并启用保护；
 * 已启用时支持修改密码。两种操作成功后都清空会话并整页跳转登录页，
 * 要求输入新密码进入。
 */
export function WebuiPasswordPanel() {
  const dashboard = useDashboard();
  const [enabled, setEnabled] = createSignal<boolean | null>(null);
  const [oldPassword, setOldPassword] = createSignal('');
  const [newPassword, setNewPassword] = createSignal('');
  const [confirmPassword, setConfirmPassword] = createSignal('');
  const [submitting, setSubmitting] = createSignal(false);

  onMount(async () => {
    try {
      const status = await api.get<{ password_enabled?: boolean }>('/api/password_status');
      if (typeof status.password_enabled === 'boolean') setEnabled(status.password_enabled);
    } catch {
      // 状态未知时保持隐藏，避免展示错误的表单
    }
  });

  const resetFields = () => {
    setOldPassword('');
    setNewPassword('');
    setConfirmPassword('');
  };

  const reloadToLogin = () => {
    window.setTimeout(() => replaceLocation('/api/login'), REDIRECT_DELAY_MS);
  };

  const validateNew = (): string | null => {
    if (!newPassword() || newPassword().length < MIN_PASSWORD_LENGTH) {
      return `新密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符`;
    }
    if (enabled() && newPassword() === oldPassword()) {
      return '新密码不能与当前密码相同';
    }
    if (newPassword() !== confirmPassword()) {
      return '两次输入的新密码不一致';
    }
    return null;
  };

  const setup = async () => {
    const invalid = validateNew();
    if (invalid) { dashboard.toast(invalid, 'warning'); return; }
    if (!await dashboard.confirm({
      title: '启用 WebUI 密码',
      message: '设置后本监控板的所有访问都需要输入密码。确认启用吗？',
      tone: 'warning',
    })) return;

    setSubmitting(true);
    try {
      await api.post('/api/webui_password/setup', {
        password: newPassword(),
        manual_confirmed: true,
      });
      dashboard.toast('密码保护已启用，正在跳转登录页…', 'success');
      resetFields();
      reloadToLogin();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '设置失败', 'danger');
    } finally {
      setSubmitting(false);
    }
  };

  const change = async () => {
    if (!oldPassword()) { dashboard.toast('请输入当前密码', 'warning'); return; }
    const invalid = validateNew();
    if (invalid) { dashboard.toast(invalid, 'warning'); return; }
    setSubmitting(true);
    try {
      await api.post('/api/plugin_change_password', {
        old_password: oldPassword(),
        new_password: newPassword(),
      });
      dashboard.toast('密码已修改，请使用新密码重新登录', 'success');
      resetFields();
      reloadToLogin();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : '修改失败', 'danger');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Show when={enabled() !== null}>
      <section class={styles['password-panel']}>
        <header class={styles['password-head']}>
          <div class={styles['password-title']}>
            <span class="material-icons" aria-hidden="true">lock</span>
            <h2>WebUI 访问密码</h2>
          </div>
          <Badge tone={enabled() ? 'success' : 'default'}>
            {enabled() ? '已启用密码保护' : '免密访问'}
          </Badge>
        </header>
        <Show
          when={enabled()}
          fallback={
            <div class={styles['password-body']}>
              <div class={styles['password-fields']}>
                <Input label="自定义密码" type="password" autocomplete="new-password"
                  value={newPassword()} onInput={(event) => setNewPassword(event.currentTarget.value)} />
                <Input label="确认新密码" type="password" autocomplete="new-password"
                  value={confirmPassword()} onInput={(event) => setConfirmPassword(event.currentTarget.value)} />
                <div class={styles['password-actions']}>
                  <Button tone="primary" icon="lock" loading={submitting()} onClick={setup}>设置并启用密码</Button>
                </div>
              </div>
              <p class={styles['password-hint']}>
                当前为免密访问。设置自定义密码后，所有访问都需要登录；临时密码（webui_initial_password）可在启用后被自定义密码取代。
              </p>
            </div>
          }
        >
          <div class={styles['password-body']}>
            <div class={styles['password-fields']}>
              <Input label="当前密码" type="password" autocomplete="current-password"
                value={oldPassword()} onInput={(event) => setOldPassword(event.currentTarget.value)} />
              <Input label="新密码" type="password" autocomplete="new-password"
                value={newPassword()} onInput={(event) => setNewPassword(event.currentTarget.value)} />
              <Input label="确认新密码" type="password" autocomplete="new-password"
                value={confirmPassword()} onInput={(event) => setConfirmPassword(event.currentTarget.value)} />
              <div class={styles['password-actions']}>
                <Button tone="primary" icon="key" loading={submitting()} onClick={change}>修改密码</Button>
              </div>
            </div>
            <p class={styles['password-hint']}>
              修改成功后会注销当前会话并跳转登录页，请使用新密码重新进入监控板。
            </p>
          </div>
        </Show>
      </section>
    </Show>
  );
}
