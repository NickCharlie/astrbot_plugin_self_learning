import { For, Show } from 'solid-js';
import { Portal } from 'solid-js/web';
import { Button } from '../ui';
import { useDashboard } from '../../stores/dashboard';
import toastStyles from './Toast.module.scss';
import dialogStyles from './Dialog.module.scss';

export function ToastViewport() {
  const dashboard = useDashboard();
  return (
    <Portal>
      <div class={toastStyles['toast-viewport']} aria-live="polite">
        <For each={dashboard.toasts()}>{(toast) =>
          <div class={`${toastStyles['toast']} ${toastStyles[`tone-${toast.tone}`] || ''}`}>
            <span class="material-icons">{toast.tone === 'danger' ? 'error' : toast.tone === 'success' ? 'check_circle' : 'info'}</span>
            <span>{toast.message}</span>
          </div>
        }</For>
      </div>
    </Portal>
  );
}

export function ConfirmDialog() {
  const dashboard = useDashboard();
  return (
    <Show when={dashboard.confirmRequest()} keyed>{(request) =>
      <Portal>
        <div class={dialogStyles['dialog-overlay']} role="presentation" onClick={(event) => event.target === event.currentTarget && dashboard.resolveConfirm(false)}>
          <section class={dialogStyles['dialog']} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
            <h2 id="confirm-title">{request.title}</h2>
            <p>{request.message}</p>
            <footer>
              <Button onClick={() => dashboard.resolveConfirm(false)}>取消</Button>
              <Button tone={request.tone || 'danger'} onClick={() => dashboard.resolveConfirm(true)}>{request.confirmText || '确认'}</Button>
            </footer>
          </section>
        </div>
      </Portal>
    }</Show>
  );
}
