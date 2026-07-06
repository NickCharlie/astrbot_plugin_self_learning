import { createMemo, createSignal, For, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { ConfigField as ConfigFieldType, ConfigGroup } from '../../types/dashboard';
import { object } from '../shared';
import { ConfigField } from '../../components/business/ConfigField';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, EmptyState, Input, Panel, Select } from '../../components/ui';
import styles from './SettingsPage.module.scss';

export function SettingsPage() {
  const dashboard = useDashboard();
  const [query, setQuery] = createSignal('');
  const [mirror, setMirror] = createSignal(localStorage.getItem('sl-pip-mirror') || 'default');
  const groups = createMemo<ConfigGroup[]>(() => {
    const schema = dashboard.schema();
    if (!schema) return [];
    if (Array.isArray(schema.groups)) return schema.groups;
    if (Array.isArray(schema.fields)) return [{ label: '基础设置', fields: schema.fields }];
    return Object.entries(object(schema.groups)).map(([key, value]) => ({ key, ...object(value) } as ConfigGroup));
  });
  const fieldsFor = (group: ConfigGroup): ConfigFieldType[] =>
    (group.fields || []).filter((field) => !query() || `${field.label || ''} ${field.key} ${field.description || ''}`.toLowerCase().includes(query().toLowerCase()));
  const dirty = createMemo(() => JSON.stringify(dashboard.config()) !== JSON.stringify(dashboard.configDraft));
  const reset = () => {
    dashboard.setConfigDraft(Object.assign({}, structuredClone(dashboard.config())));
    dashboard.toast('未保存改动已重置', 'default');
  };
  const install = async (tier: 'basic' | 'full') => {
    if (!await dashboard.confirm({ title: '安装 Python 依赖', message: `即将调用 pip 安装${tier === 'basic' ? '基础' : '全能力'}依赖，确定继续吗？`, tone: 'warning' })) return;
    dashboard.setBusy(true);
    try {
      await api.post('/api/dependencies/install', {
        manual_confirmed: true,
        source: 'webui_settings',
        tier,
        pip_mirror: mirror(),
      });
      dashboard.toast('依赖安装任务已完成', 'success');
    } catch (caught) { dashboard.toast(caught instanceof Error ? caught.message : '依赖安装失败', 'danger'); }
    finally { dashboard.setBusy(false); }
  };
  return (
    <div class="page">
      <PageHeader title="设置" description="编辑插件配置，并在明确确认后安装可选依赖。" icon="tune" actions={
        <div class="inline-actions">
          <Button icon="refresh" onClick={dashboard.loadConfig}>重新加载</Button>
          <Button disabled={!dirty()} onClick={reset}>重置</Button>
          <Button tone="primary" icon="save" loading={dashboard.busy()} disabled={!dashboard.schema() || !dirty()} onClick={dashboard.saveConfig}>手动保存设置</Button>
        </div>
      } />
      <Panel title="手动安装依赖" hint="不会在插件安装或启动时自动执行">
        <div class={styles['dependency-panel']}>
          <Select label="pip 镜像源" value={mirror()} onChange={(event) => { setMirror(event.currentTarget.value); localStorage.setItem('sl-pip-mirror', event.currentTarget.value); }}>
            <option value="default">PyPI 默认源</option><option value="tsinghua">清华大学 TUNA</option><option value="aliyun">阿里云</option><option value="tencent">腾讯云</option><option value="ustc">中国科大 USTC</option><option value="douban">豆瓣</option>
          </Select>
          <div class="inline-actions"><Button icon="bolt" onClick={() => install('basic')}>基础能力依赖</Button><Button tone="primary" icon="deployed_code" onClick={() => install('full')}>全能力依赖</Button></div>
        </div>
      </Panel>
      <Show when={dashboard.schema()} fallback={<EmptyState title="配置面板尚未加载" action={<Button onClick={dashboard.loadConfig}>加载配置</Button>} />}>
        <div class={styles['settings-toolbar']}><Input placeholder="搜索配置项" value={query()} onInput={(event) => setQuery(event.currentTarget.value)} /></div>
        <div class={styles['settings-groups']}>
          <For each={groups()}>{(group) =>
            <Show when={fieldsFor(group).length}>
              <Panel title={group.label || group.name || String(group.title || group.key || '设置分组')} hint={String(group.description ?? group.hint ?? '')}>
                <div class={styles['config-grid']}><For each={fieldsFor(group)}>{(field) => <ConfigField field={field} />}</For></div>
              </Panel>
            </Show>
          }</For>
        </div>
      </Show>
    </div>
  );
}
