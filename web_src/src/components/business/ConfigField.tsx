import { For, Show } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import type { ConfigField as ConfigFieldType } from '../../types/dashboard';
import { normalizeFieldValue } from '../../lib/config';
import { Input, Select, Textarea } from '../ui';

const optionValue = (option: unknown) =>
  option && typeof option === 'object' && 'value' in option ? (option as { value: unknown }).value : option;
const optionLabel = (option: unknown) =>
  option && typeof option === 'object' && 'label' in option
    ? String((option as { label?: unknown }).label ?? optionValue(option))
    : String(option);

export function ConfigField(props: { field: ConfigFieldType }) {
  const dashboard = useDashboard();
  const value = () => dashboard.configDraft[props.field.key];
  const update = (next: unknown) => dashboard.setConfigDraft(props.field.key, normalizeFieldValue(props.field, next));
  const label = () => props.field.label || props.field.key;
  const hint = () => String(props.field.description ?? props.field.hint ?? '');
  const readonly = () => props.field.editable === false || props.field.widget === 'readonly';
  const options = () => {
    const providerType = String(props.field.provider_type || '').trim().toLowerCase();
    const byType = dashboard.schema()?.provider_options_by_type || {};
    const typed = providerType && Array.isArray(byType[providerType]) ? byType[providerType] : [];
    const source = typed.length ? typed : props.field.options || [];
    return source.filter((option) => {
      if (!providerType || !option || typeof option !== 'object') return true;
      const optionType = String((option as Record<string, unknown>).provider_type || '').trim().toLowerCase();
      return !optionType || optionType === providerType;
    });
  };
  return (
    <Show
      when={!['boolean', 'bool'].includes(props.field.type || '') && !['switch', 'toggle'].includes(props.field.widget || '')}
      fallback={
        <label class="switch-field">
          <span><strong>{label()}</strong><Show when={hint()}><small>{hint()}</small></Show></span>
          <input type="checkbox" disabled={readonly()} checked={Boolean(value())} onChange={(event) => update(event.currentTarget.checked)} />
          <i />
        </label>
      }
    >
      <Show
        when={options().length === 0 && props.field.widget !== 'select'}
        fallback={
          <Select label={label()} hint={hint()} disabled={readonly()} value={String(value() ?? '')} onChange={(event) => update(event.currentTarget.value)}>
            <For each={options()}>{(option) => <option value={String(optionValue(option))}>{optionLabel(option)}</option>}</For>
          </Select>
        }
      >
        <Show
          when={props.field.widget !== 'textarea' && props.field.type !== 'json' && props.field.type !== 'array'}
          fallback={
            <Textarea
              label={label()} hint={hint()} rows={props.field.type === 'json' ? 8 : 4}
              readOnly={readonly()}
              value={typeof value() === 'string' ? String(value()) : Array.isArray(value()) ? (value() as unknown[]).join('\n') : JSON.stringify(value() ?? {}, null, 2)}
              onInput={(event) => update(event.currentTarget.value)}
            />
          }
        >
          <Input
            label={label()} hint={hint()}
            type={['integer', 'int', 'number', 'float'].includes(props.field.type || '') ? 'number' : 'text'}
            min={props.field.min} max={props.field.max} value={String(value() ?? '')}
            readOnly={readonly()}
            onInput={(event) => update(event.currentTarget.value)}
          />
        </Show>
      </Show>
    </Show>
  );
}
