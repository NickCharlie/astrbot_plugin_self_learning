import { createEffect, onCleanup, Show, type JSX } from 'solid-js';
import { Portal } from 'solid-js/web';
import { Button } from '../ui';
import styles from './DetailDialog.module.scss';

export function DetailDialog(props: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: JSX.Element;
}) {
  let dialogRef: HTMLElement | undefined;
  let previousFocus: Element | null = null;
  createEffect(() => {
    if (!props.open) return;
    previousFocus = document.activeElement;
    queueMicrotask(() => dialogRef?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        props.onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef) return;
      // 把 Tab 焦点限制在对话框内，避免键盘用户走到遮罩后的页面（Sourcery review）
      const focusables = Array.from(
        dialogRef.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'),
      );
      if (!focusables.length) {
        event.preventDefault();
        dialogRef.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    onCleanup(() => {
      document.removeEventListener('keydown', onKeyDown);
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    });
  });
  return (
    <Show when={props.open}>
      <Portal>
        <div
          class={styles['overlay']}
          role="presentation"
          onClick={(event) => event.target === event.currentTarget && props.onClose()}
        >
          <section ref={dialogRef} class={styles['dialog']} role="dialog" aria-modal="true" aria-label={props.title} tabIndex={-1}>
            <header class={styles['head']}>
              <h2>{props.title}</h2>
              <Button size="sm" onClick={props.onClose}>关闭</Button>
            </header>
            <div class={styles['body']}>{props.children}</div>
          </section>
        </div>
      </Portal>
    </Show>
  );
}
