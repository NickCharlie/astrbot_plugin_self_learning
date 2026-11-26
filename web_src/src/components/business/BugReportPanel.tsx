import { createSignal, For, onMount, Show } from 'solid-js';
import { api } from '../../services/api';
import { useDashboard } from '../../stores/dashboard';
import { object } from '../../pages/shared';
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
const FALLBACK_OS: Option[] = [
  { value: 'Linux', label: 'Linux' }, { value: 'Windows', label: 'Windows' },
  { value: 'macOS', label: 'macOS' }, { value: 'Docker', label: 'Docker' },
];

// 模板的 os 是必填下拉，只能取固定选项；按浏览器推断报告者环境（不是服务器环境）
const detectClientOs = (): string => {
  const ua = typeof navigator === 'undefined' ? '' : navigator.userAgent;
  // jsdom 报告的是 "Mozilla/5.0 (win32) …"，真实浏览器是 "Windows NT 10.0"，两者都认
  if (/Windows|win32|win64/i.test(ua)) return 'Windows';
  if (/Mac OS X|Macintosh|darwin/i.test(ua)) return 'macOS';
  if (/Linux|X11|Android|CrOS/i.test(ua)) return 'Linux';
  return '';
};

// 后端 /api/bug_report/{config,history} 与提交接口一直存在，但 WebUI 没有入口。
export function BugReportPanel() {
  const dashboard = useDashboard();
  const [config, setConfig] = createSignal<Record<string, unknown>>({});
  const [title, setTitle] = createSignal('');
  const [description, setDescription] = createSignal('');
  const [steps, setSteps] = createSignal('');
  const [expected, setExpected] = createSignal('');
  const [severity, setSeverity] = createSignal('3');
  const [priority, setPriority] = createSignal('3');
  const [type, setType] = createSignal('codeerror');
  const [build, setBuild] = createSignal('');
  const [os, setOs] = createSignal(detectClientOs());
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

  const load = async () => {
    try {
      const payload = await api.get<Record<string, unknown>>('/api/bug_report/config');
      setConfig(payload);
      // 用户可能已经手动填写，仅在为空时回填默认版本
      setBuild((current) => current.trim() ? current : String(payload.defaultBuild ?? ''));
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : 'Bug 报告配置加载失败', 'danger');
    }
  };
  onMount(load);

  const submit = async () => {
    // description / expected 在模板里是必填项，这里先拦住，避免打开后面对空白必填框
    if (!title().trim() || !steps().trim() || !description().trim() || !expected().trim()) {
      return dashboard.toast('请填写 Bug 标题、问题描述、重现步骤和期望行为', 'warning');
    }
    if (!os().trim()) {
      return dashboard.toast('请选择操作系统', 'warning');
    }
    setBusy(true);
    try {
      const result = await api.post<{ message?: string; data?: { url?: string } }>('/api/bug_report', {
        title: title().trim(),
        description: description().trim(),
        steps: steps().trim(),
        expected: expected().trim(),
        severity: Number(severity()),
        pri: Number(priority()),
        type: type(),
        build: build().trim() || String(config().defaultBuild ?? ''),
        os: os().trim(),
        browser: browser().trim(),
        mailto: mailto().trim(),
      });
      // 后端只拼预填链接，真正的提交在 GitHub 上由用户确认
      const url = result.data?.url;
      if (!url) {
        return dashboard.toast(result.message || '已生成反馈链接', 'warning');
      }
      // 弹窗可能被浏览器拦截；只有确实打开了标签页才清空草稿
      const opened = window.open(url, '_blank', 'noopener');
      if (opened) {
        dashboard.toast('已在新标签页打开 GitHub 反馈页，请确认后提交', 'success');
        setTitle('');
        setDescription('');
        setSteps('');
        setExpected('');
      } else {
        dashboard.toast(`浏览器拦截了新标签页，请手动打开：${url}`, 'warning');
      }
    } catch (caught) {
      dashboard.toast(caught instanceof Error ? caught.message : 'Bug 反馈链接生成失败', 'danger');
    } finally { setBusy(false); }
  };

  return (
    <Panel
      title="Bug 反馈"
      hint="填写后跳转 GitHub 按模板提交；请尽量提供可复现步骤"
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
          <Select label="操作系统" value={os()} onChange={(event) => setOs(event.currentTarget.value)}>
            <For each={options('osOptions', FALLBACK_OS)}>{(option) => <option value={String(option.value)}>{option.label}</option>}</For>
          </Select>
          <Input label="浏览器" value={browser()} onInput={(event) => setBrowser(event.currentTarget.value)} />
          <Input label="联系邮箱（可选，会公开在 issue 中）" value={mailto()} onInput={(event) => setMailto(event.currentTarget.value)} />
        </div>
        <Textarea label="问题描述" rows={4} value={description()} onInput={(event) => setDescription(event.currentTarget.value)} placeholder="发生了什么？" />
        <Textarea label="重现步骤" rows={6} value={steps()} onInput={(event) => setSteps(event.currentTarget.value)} placeholder={'1. 打开 WebUI\n2. 点击某个按钮\n3. 观察到异常'} />
        <Textarea label="期望行为" rows={3} value={expected()} onInput={(event) => setExpected(event.currentTarget.value)} placeholder="你期望发生什么？" />
        <Show when={logEntries().length}>
          <details class={styles['log-preview']}>
            <summary>附加日志预览（{logEntries().length} 项，仅展示，不会随报告提交）</summary>
            <For each={logEntries()}>{([name, content]) => <>
              <h4>{name}</h4>
              <pre>{content}</pre>
            </>}</For>
          </details>
        </Show>
        <div class="inline-actions">
          <Button tone="primary" icon="open_in_new" loading={busy()} onClick={submit}>打开 GitHub 反馈页</Button>
        </div>
      </Show>
    </Panel>
  );
}
