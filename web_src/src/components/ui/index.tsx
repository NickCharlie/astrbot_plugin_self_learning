import { For, Show, splitProps, onMount, type JSX, type ParentProps } from 'solid-js';
import type { Tone } from '../../types/dashboard';
import buttonStyles from './Button.module.scss';
import spinnerStyles from './Spinner.module.scss';
import cardStyles from './Card.module.scss';
import panelStyles from './Panel.module.scss';
import statCardStyles from './StatCard.module.scss';
import badgeStyles from './Badge.module.scss';
import progressStyles from './ProgressBar.module.scss';
import fieldStyles from './FormField.module.scss';
import switchStyles from './SwitchField.module.scss';
import segmentedStyles from './Segmented.module.scss';
import paginationStyles from './Pagination.module.scss';
import stateStyles from './StateView.module.scss';

type ButtonProps = ParentProps<JSX.ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: Tone;
  size?: 'sm' | 'md';
  loading?: boolean;
  icon?: string;
}>;

export function Button(props: ButtonProps) {
  const [local, button] = splitProps(props, ['children', 'tone', 'size', 'loading', 'icon', 'class']);
  const toneCls = () => buttonStyles[`tone-${local.tone || 'default'}`] || '';
  const sizeCls = () => buttonStyles[`size-${local.size || 'md'}`] || '';
  return (
    <button
      {...button}
      class={`${buttonStyles['ui-button']} ${toneCls()} ${sizeCls()} ${local.class || ''}`}
      disabled={local.loading || button.disabled}
    >
      <Show when={local.loading}><span class={spinnerStyles['ui-spinner']} aria-hidden="true" /></Show>
      <Show when={local.icon}><span class="material-icons" aria-hidden="true">{local.icon}</span></Show>
      <span>{local.children}</span>
    </button>
  );
}

export function IconButton(props: Omit<ButtonProps, 'children'> & { icon: string; label: string }) {
  return <Button {...props} class={`${buttonStyles['icon-only']} ${props.class || ''}`} title={props.label} aria-label={props.label} />;
}

export function Card(props: ParentProps<{ class?: string; interactive?: boolean }>) {
  return <div class={`${cardStyles['ui-card']} ${props.interactive ? cardStyles['interactive'] : ''} ${props.class || ''}`}>{props.children}</div>;
}

export function Panel(props: ParentProps<{
  title?: string;
  hint?: string;
  icon?: string;
  actions?: JSX.Element;
  class?: string;
}>) {
  return (
    <section class={`${panelStyles['ui-panel']} ${props.class || ''}`}>
      <Show when={props.title || props.actions}>
        <header class={panelStyles['ui-panel-head']}>
          <div>
            <Show when={props.title}><h2><Show when={props.icon}><span class="material-icons">{props.icon}</span></Show>{props.title}</h2></Show>
            <Show when={props.hint}><p>{props.hint}</p></Show>
          </div>
          <div class={panelStyles['ui-panel-actions']}>{props.actions}</div>
        </header>
      </Show>
      <div class={panelStyles['ui-panel-body']}>{props.children}</div>
    </section>
  );
}

export function StatCard(props: { label: string; value: string | number; note?: string; tone?: Tone; icon?: string }) {
  return (
    <Card class={statCardStyles['stat-card']}>
      <div class={statCardStyles['stat-card-label']}>
        <Show when={props.icon}><span class="material-icons">{props.icon}</span></Show>{props.label}
      </div>
      <strong>{props.value}</strong>
      <Show when={props.note}><small>{props.note}</small></Show>
    </Card>
  );
}

export function Badge(props: ParentProps<{ tone?: Tone }>) {
  const toneCls = () => badgeStyles[`tone-${props.tone || 'default'}`] || '';
  return <span class={`${badgeStyles['ui-badge']} ${toneCls()}`}>{props.children}</span>;
}

export function ProgressBar(props: { value: number; label?: string; tone?: Tone }) {
  const value = () => Math.max(0, Math.min(100, props.value));
  const toneCls = () => progressStyles[`tone-${props.tone || 'primary'}`] || '';
  return (
    <div class={progressStyles['progress-wrap']}>
      <Show when={props.label}><div class={progressStyles['progress-label']}><span>{props.label}</span><b>{value().toFixed(0)}%</b></div></Show>
      <div class={progressStyles['progress-track']}><span class={toneCls()} style={{ width: `${value()}%` }} /></div>
    </div>
  );
}

type FieldProps = { label?: string; hint?: string; error?: string; class?: string };

function Field(props: ParentProps<FieldProps>) {
  return (
    <label class={`${fieldStyles['ui-field']} ${props.class || ''}`}>
      <Show when={props.label}><span class={fieldStyles['ui-field-label']}>{props.label}</span></Show>
      {props.children}
      <Show when={props.hint}><small>{props.hint}</small></Show>
      <Show when={props.error}><small class={fieldStyles['field-error']}>{props.error}</small></Show>
    </label>
  );
}

export function Input(props: JSX.InputHTMLAttributes<HTMLInputElement> & FieldProps) {
  const [local, input] = splitProps(props, ['label', 'hint', 'error', 'class']);
  return <Field {...local}><input {...input} /></Field>;
}

export function Select(props: ParentProps<JSX.SelectHTMLAttributes<HTMLSelectElement> & FieldProps>) {
  const [local, select] = splitProps(props, ['label', 'hint', 'error', 'class', 'children']);
  let element: HTMLSelectElement | undefined;
  // Solid 会先应用 value 属性、后插入 <For> 渲染的 option，真实浏览器对无选项的
  // select 设置 value 不生效，导致回退选中第一项（issue #243）。挂载后再同步一次。
  onMount(() => {
    if (element && select.value !== undefined) element.value = String(select.value ?? '');
  });
  return <Field {...local}><select ref={element} {...select}>{local.children}</select></Field>;
}

export function Textarea(props: JSX.TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps) {
  const [local, textarea] = splitProps(props, ['label', 'hint', 'error', 'class']);
  return <Field {...local}><textarea {...textarea} /></Field>;
}

export function SegmentedControl<T extends string>(props: {
  value: T;
  options: Array<{ value: T; label: string; icon?: string }>;
  onChange: (value: T) => void;
  label?: string;
}) {
  return (
    <div class={segmentedStyles['segmented']} role="group" aria-label={props.label}>
      <For each={props.options}>{(option) =>
        <button classList={{ [segmentedStyles['active']]: option.value === props.value }} onClick={() => props.onChange(option.value)}>
          <Show when={option.icon}><span class="material-icons">{option.icon}</span></Show>{option.label}
        </button>
      }</For>
    </div>
  );
}

export function Pagination(props: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  disabled?: boolean;
}) {
  return (
    <nav class={paginationStyles['pagination']} aria-label="分页">
      <Button size="sm" icon="chevron_left" disabled={props.disabled || props.page <= 1} onClick={() => props.onChange(props.page - 1)}>上一页</Button>
      <span>第 {props.page} / {Math.max(1, props.totalPages)} 页</span>
      <Button size="sm" icon="chevron_right" disabled={props.disabled || props.page >= props.totalPages} onClick={() => props.onChange(props.page + 1)}>下一页</Button>
    </nav>
  );
}

export function LoadingState(props: { label?: string }) {
  return <div class={stateStyles['state-view']}><span class={spinnerStyles['ui-spinner']} /><p>{props.label || '正在加载…'}</p></div>;
}

export function EmptyState(props: { title?: string; detail?: string; icon?: string; action?: JSX.Element }) {
  return (
    <div class={`${stateStyles['state-view']} ${stateStyles['empty'] || ''}`}>
      <span class="material-icons">{props.icon || 'inbox'}</span>
      <strong>{props.title || '暂无数据'}</strong>
      <Show when={props.detail}><p>{props.detail}</p></Show>
      {props.action}
    </div>
  );
}

export function ErrorState(props: { message: string; retry?: () => void }) {
  return <EmptyState icon="error_outline" title="加载失败" detail={props.message} action={props.retry && <Button onClick={props.retry}>重试</Button>} />;
}
