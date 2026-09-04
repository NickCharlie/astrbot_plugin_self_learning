import { createMemo, createSignal, For, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import type { ConfigField as ConfigFieldType, ConfigGroup } from '../../types/dashboard';
import { object } from '../shared';
import { ConfigField } from '../../components/business/ConfigField';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge, Button, EmptyState, Input, Select } from '../../components/ui';
import styles from './SettingsPage.module.scss';

export function SettingsPage() {
  const dashboard = useDashboard();
  const [query, setQuery] = createSignal('');
  const [selectedKey, setSelectedKey] = createSignal(localStorage.getItem('sl-settings-group') || '');
  const [mirror, setMirror] = createSignal(localStorage.getItem('sl-pip-mirror') || 'default');
  const groups = createMemo<ConfigGroup[]>(() => {
    const schema = dashboard.schema();
    if (!schema) return [];
    if (Array.isArray(schema.groups)) return schema.groups;
    if (Array.isArray(schema.fields)) return [{ label: '基础设置', fields: schema.fields }];
    return Object.entries(object(schema.groups)).map(([key, value]) => ({ key, ...object(value) } as ConfigGroup));
  });
  const groupKey = (group: ConfigGroup) => String(group.key ?? group.label ?? group.name ?? group.title ?? '');
  const groupLabel = (group: ConfigGroup) => String(group.label || group.name || group.title || groupKey(group) || '设置分组');
  const groupHint = (group: ConfigGroup) => String(group.description ?? group.hint ?? '');
  const fieldMatches = (field: ConfigFieldType, q: string) =>
    `${field.label || ''} ${field.key} ${field.description || ''}`.toLowerCase().includes(q);
  const fieldsFor = (group: ConfigGroup): ConfigFieldType[] =>
    (group.fields || []).filter((field) => !query() || fieldMatches(field, query().toLowerCase()));
  const matchedGroups = createMemo(() => groups().filter((group) => fieldsFor(group).length));

  const dirtyKeys = createMemo(() => {
    const saved = dashboard.config();
    return new Set(
      Object.keys(dashboard.configDraft).filter(
        (key) => JSON.stringify(dashboard.configDraft[key]) !== JSON.stringify(saved[key]),
      ),
    );
  });
  const groupDirty = (group: ConfigGroup) => (group.fields || []).some((field) => dirtyKeys().has(field.key));

  const activeGroup = createMemo(() => {
    const matched = matchedGroups();
    return matched.find((group) => groupKey(group) === selectedKey()) || matched[0];
  });
  const select = (key: string) => {
    setSelectedKey(key);
    localStorage.setItem('sl-settings-group', key);
  };

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
          <Show when={dirtyKeys().size}>
            <Badge tone="warning">未保存 {dirtyKeys().size} 项</Badge>
          </Show>
          <Button icon="refresh" onClick={dashboard.loadConfig}>重新加载</Button>
          <Button disabled={!dirtyKeys().size} onClick={reset}>重置</Button>
          <Button tone="primary" icon="save" loading={dashboard.busy()} disabled={!dashboard.schema() || !dirtyKeys().size} onClick={dashboard.saveConfig}>手动保存设置</Button>
        </div>
      } />
      <div class={styles['settings-layout']}>
        <aside class={styles['group-nav']}>
          <Show when={dashboard.schema()} fallback={<p class={styles['no-match']}>配置面板尚未加载。</p>}>
            <Input placeholder="搜索配置项" value={query()} onInput={(event) => setQuery(event.currentTarget.value)} />
            <nav class={styles['group-list']} aria-label="设置分组">
              <For each={matchedGroups()}>{(group) =>
                <button
                  type="button"
                  classList={{ [styles['group-item']]: true, [styles['active']]: !query() && activeGroup() === group }}
                  onClick={() => select(groupKey(group))}
                >
                  <span class={styles['group-item-label']}>{groupLabel(group)}</span>
                  <span class={styles['group-item-meta']}>
                    <Show when={groupDirty(group)}><span class={styles['dirty-dot']} title="有未保存修改" /></Show>
                    <span>{(group.fields || []).length}</span>
                  </span>
                </button>
              }</For>
              <Show when={!matchedGroups().length}>
                <p class={styles['no-match']}>没有匹配「{query()}」的配置项</p>
              </Show>
            </nav>
          </Show>
          <div class={styles['dep-block']}>
            <span class={styles['dep-title']}>依赖安装</span>
            <Select label="pip 镜像源" value={mirror()} onChange={(event) => { setMirror(event.currentTarget.value); localStorage.setItem('sl-pip-mirror', event.currentTarget.value); }}>
              <option value="default">PyPI 默认源</option><option value="tsinghua">清华大学 TUNA</option><option value="aliyun">阿里云</option><option value="tencent">腾讯云</option><option value="ustc">中国科大 USTC</option><option value="douban">豆瓣</option>
            </Select>
            <p class={styles['dep-hint']}>不会在插件安装或启动时自动执行。</p>
            <div class="inline-actions">
              <Button size="sm" icon="bolt" onClick={() => install('basic')}>基础能力依赖</Button>
              <Button size="sm" tone="primary" icon="deployed_code" onClick={() => install('full')}>全能力依赖</Button>
            </div>
          </div>
        </aside>
        <section class={styles['group-detail']} aria-live="polite">
          <Show when={dashboard.schema()} fallback={<EmptyState title="配置面板尚未加载" action={<Button onClick={dashboard.loadConfig}>加载配置</Button>} />}>
            <Show
              when={!query()}
              fallback={
                <Show when={matchedGroups().length} fallback={
                  <EmptyState icon="search_off" title="没有匹配的配置项" detail={`没有找到与「${query()}」相关的配置，换个关键词试试。`} />
                }>
                  <div class={styles['search-results']}>
                    <For each={matchedGroups()}>{(group) => <>
                      <h3 class={styles['result-group']}>{groupLabel(group)}</h3>
                      <div class={styles['config-grid']}><For each={fieldsFor(group)}>{(field) => <ConfigField field={field} />}</For></div>
                    </>}</For>
                  </div>
                </Show>
              }
            >
              <Show when={activeGroup()} fallback={<EmptyState title="没有匹配的配置项" detail="调整搜索关键词后重试。" />}>
                <div class={styles['detail-head']}>
                  <div>
                    <h3>{groupLabel(activeGroup()!)}</h3>
                    <Show when={groupHint(activeGroup()!)}><p>{groupHint(activeGroup()!)}</p></Show>
                  </div>
                  <span class={styles['field-count']}>{fieldsFor(activeGroup()!).length} 项</span>
                </div>
                <div class={styles['config-grid']}><For each={fieldsFor(activeGroup()!)}>{(field) => <ConfigField field={field} />}</For></div>
              </Show>
            </Show>
          </Show>
        </section>
      </div>
    </div>
  );
}
