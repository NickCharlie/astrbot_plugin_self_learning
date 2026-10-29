import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { list, object } from '../../pages/shared';
import { formatTime, textOrDash } from '../../lib/format';
import { Button, EmptyState, Input, Panel, Select, Textarea } from '../ui';
import styles from './BugReportPanel.module.scss';

type Option = { value: string | number; label: string };

const FALLBACK_SEVERITY: Option[] = [
  { value: 1, label: '1 - 致命' }, { value: 2, label: '2 - 严重' },
  { value: 3, label: '3 - 一般' }, { value: 4, label: '4 - 轻微' },
];
const FALLBACK_PRIORITY: Option[] = [
  { value: 1, label: '1 - 紧急' }, { value: 2, label: '2 - 高' },
  { value: 3, label: '3 - 中' }, { value: 4, label: '4 - 低' },
];
const FALLBACK_TYPE: Option[] = [
  { value: 'codeerror', label: '代码错误' }, { value: 'config', label: '配置相关' },
  { value: 'install', label: '安装部署' }, { value: 'performance', label: '性能问题' },
  { value: 'others', label: '其他' },
];

// 后端 /api/bug_report/{config,history} 与提交接口一直存在，但 WebUI 没有入口。
export function BugReportPanel() {
  const dashboard = useDashboard();
  const [config, setConfig] = createSignal<Record<string, unknown>>({});
  const [history, setHistory] = createSignal<Record<string, unknown>[]>([]);
  const [title, setTitle] = createSignal('');
  const [steps, setSteps] = createSignal('');
  const [severity, setSeverity] = createSignal('3');
  const [priority, setPriority] = createSignal('3');
  const [type, setType] = createSignal('codeerror');
  const [build, setBuild] = createSignal('');
  const [os, setOs] = createSignal('');
  const [browser, setBrowser] = createSignal('');
  const [mailto, setMailto] = createSignal('');
  const [busy, setBusy] = createSignal(false);

  const options = (key: string, fallback: Option[]): Option[] => {
    const value = config()[key];
    return Array.isArray(value) && value.length ? value as Option[] : fallback;
  };
  const logEntries = (): Array<[string, string]> =>
    Object.entries(object(config().logPreview))
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0);

  const loadHistory = async () => {
    const payload = await api.get<Record<string, unknown>>('/api/bug_report/history?limit=10');
    setHistory(list<Record<string, unknown>>(payload.history ?? payload));
  };
  const load = async () => {
    try {
      const payload = await api.get<Record<string, unknown>>('/api/bug_report/config');
      setConfig(payload);
      // 用户可能已经手动填写，仅在为空时回填默认版本
      setBuild((current) => current.trim() ? current : String(payload.defaultBuild ?? ''));
      await loadHistory();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : 'Bug 报告配置加载失败', 'danger');
    }
  };
  onMount(load);

  const submit = async () => {
    if (!title().trim() || !steps().trim()) {
      return dashboard.toast('请填写 Bug 标题和重现步骤', 'warning');
    }
    setBusy(true);
    try {
      const result = await api.post<{ message?: string }>('/api/bug_report', {
        title: title().trim(),
        steps: steps().trim(),
        severity: Number(severity()),
        pri: Number(priority()),
        type: type(),
        build: build().trim() || String(config().defaultBuild ?? ''),
        os: os().trim(),
        browser: browser().trim(),
        mailto: mailto().trim(),
      });
      dashboard.toast(result.message || 'Bug 报告已提交', 'success');
      setTitle('');
      setSteps('');
      await loadHistory();
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : 'Bug 报告提交失败', 'danger');
    } finally { setBusy(false); }
  };

  return (
    <Panel
      title="Bug 反馈"
      hint="提交到官方禅道；请尽量提供可复现步骤"
      icon="bug_report"
      actions={<Button icon="refresh" onClick={load}>刷新</Button>}
    >
      <Show when={config().enabled !== false} fallback={<EmptyState title="Bug 反馈暂不可用" detail={String(config().message ?? '管理员未开启该功能。')} />}>
        <div class={styles['form-grid']}>
          <Input label="Bug 标题" value={title()} onInput={(event) => setTitle(event.currentTarget.value)} />
          <Select label="严重程度" value={severity()} onChange={(event) => setSeverity(event.currentTarget.value)}>
            <For each={options('severityOptions', FALLBACK_SEVERITY)}>{(option) => <option value={String(option.value)}>{option.label}</option>}</For>
          </Select>
          <Select label="优先级" value={priority()} onChange={(event) => setPriority(event.currentTarget.value)}>
            <For each={options('priorityOptions', FALLBACK_PRIORITY)}>{(option) => <option value={String(option.value)}>{option.label}</option>}</For>
          </Select>
          <Select label="类型" value={type()} onChange={(event) => setType(event.currentTarget.value)}>
            <For each={options('typeOptions', FALLBACK_TYPE)}>{(option) => <option value={String(option.value)}>{option.label}</option>}</For>
          </Select>
          <Input label="影响版本" value={build()} onInput={(event) => setBuild(event.currentTarget.value)} />
          <Input label="操作系统" value={os()} onInput={(event) => setOs(event.currentTarget.value)} />
          <Input label="浏览器" value={browser()} onInput={(event) => setBrowser(event.currentTarget.value)} />
          <Input label="联系邮箱（可选）" value={mailto()} onInput={(event) => setMailto(event.currentTarget.value)} />
        </div>
        <Textarea label="重现步骤" rows={6} value={steps()} onInput={(event) => setSteps(event.currentTarget.value)} placeholder={'1. 打开 WebUI\n2. 点击某个按钮\n3. 观察到异常'} />
        <Show when={logEntries().length}>
          <details class={styles['log-preview']}>
            <summary>附加日志预览（{logEntries().length} 项）</summary>
            <For each={logEntries()}>{([name, content]) => <>
              <h4>{name}</h4>
              <pre>{content}</pre>
            </>}</For>
          </details>
        </Show>
        <div class="inline-actions">
          <Button tone="primary" icon="send" loading={busy()} onClick={submit}>提交 Bug 报告</Button>
        </div>
      </Show>
      <Show when={history().length}>
        <h4 class={styles['history-title']}>最近提交</h4>
        <div class="data-list">
          <For each={history()}>{(item) =>
            <div class="check-row">
              <div>
                <strong>{textOrDash(item.title ?? item.id ?? 'Bug 报告')}</strong>
                <small>{formatTime(item.created_at ?? item.timestamp)}</small>
              </div>
              <span>{textOrDash(item.status ?? item.message)}</span>
            </div>
          }</For>
        </div>
      </Show>
    </Panel>
  );
}
