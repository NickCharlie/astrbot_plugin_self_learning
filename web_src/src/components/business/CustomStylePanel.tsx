import { Show, createSignal } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { applyCustomCss, loadCustomCss, resetCustomStyle } from '../../lib/customStyle';
import { reloadPage } from '../../lib/navigation';
import { Badge, Button } from '../ui';
import styles from './CustomStylePanel.module.scss';

const EXAMPLE_CSS = `/* 示例：覆盖全局设计变量（强调色/圆角/密度） */
#slx-app {
  --primary: #2f7fd1;
  --accent: #2f7fd1;
  --radius: 4px;
}

/* 示例：面板直角 + 加粗发丝线 */
.slx-panel {
  border-radius: 4px;
  border-width: 1.5px;
}`;

/** 面板里挂载的 slx- 稳定钩子清单（独一无二前缀，专供用户 CSS 定位）。 */
const HOOK_LIST: Array<[string, string]> = [
  ['#slx-app', '应用根容器（在此覆盖设计变量最省力）'],
  ['slx-topbar / slx-brand / slx-toolbar', '顶栏 / 品牌区 / 工具栏'],
  ['slx-nav / slx-nav-item / slx-nav-item-active', '导航条 / 导航项 / 激活项'],
  ['slx-page-header / slx-page-title', '页头 / 页标题'],
  ['slx-panel(-head/-title/-body)', '面板骨架'],
  ['slx-card / slx-card-interactive', '卡片'],
  ['slx-btn / slx-btn-primary|success|warning|danger / slx-btn-sm', '按钮及色调'],
  ['slx-stat / slx-stat-label / slx-stat-value', '统计卡'],
  ['slx-badge / slx-field / slx-field-label / slx-input', '徽标 / 表单'],
  ['slx-segmented / slx-progress(-track/-fill)', '分段控件 / 进度条'],
  ['slx-dialog(-overlay) / slx-toast', '对话框 / 提示条'],
  ['slx-hero / slx-module-card / slx-entry-card', '首页主视觉 / 模块卡 / 入口卡'],
  ['slx-password-panel / slx-reminder / slx-state', '密码面板 / 免密提醒 / 状态视图'],
];

export function CustomStylePanel() {
  const dashboard = useDashboard();
  const [css, setCss] = createSignal(loadCustomCss());
  const [saved, setSaved] = createSignal(Boolean(loadCustomCss().trim()));

  const save = () => {
    applyCustomCss(css());
    setSaved(Boolean(css().trim()));
    dashboard.toast(css().trim() ? '自定义样式已应用' : '自定义样式已清空', 'success');
  };

  const reset = async () => {
    if (!await dashboard.confirm({
      title: '重置默认风格',
      message: '将清除自定义 CSS 并恢复默认主题，页面随后刷新。确定继续吗？',
      tone: 'warning',
    })) return;
    resetCustomStyle();
    setCss('');
    setSaved(false);
    dashboard.toast('已恢复默认风格，正在刷新…', 'success');
    window.setTimeout(reloadPage, 600);
  };

  return (
    <section class={`slx-style-panel ${styles['style-panel']}`}>
      <header class={styles['style-head']}>
        <div class={styles['style-title']}>
          <span class="material-icons" aria-hidden="true">palette</span>
          <h2>自定义样式 (CSS)</h2>
        </div>
        <Show when={saved()}>
          <Badge tone="success">已启用</Badge>
        </Show>
      </header>
      <div class={styles['style-body']}>
        <textarea
          class={styles['style-editor']}
          spellcheck={false}
          rows={10}
          aria-label="自定义 CSS"
          placeholder={EXAMPLE_CSS}
          value={css()}
          onInput={(event) => setCss(event.currentTarget.value)}
        />
        <div class="inline-actions">
          <Button tone="primary" icon="check" onClick={save}>保存并应用</Button>
          <Button icon="restart_alt" onClick={reset}>重置默认风格</Button>
          <span class={styles['style-note']}>保存即时生效，无需刷新；样式保存在本浏览器中。</span>
        </div>
        <details class={styles['style-docs']}>
          <summary>可用样式钩子（slx- 前缀，独一无二命名，不会与其它样式互相干扰）</summary>
          <ul>
            {HOOK_LIST.map(([hook, desc]) => <li><code>{hook}</code> — {desc}</li>)}
          </ul>
          <p>
            页面级作用域：<code>[data-page='monitoring'] .slx-panel {'{ … }'}</code>；
            设计变量：<code>--bg / --surface / --text / --muted / --border / --primary / --accent / --radius(-sm/-lg) / --duration</code> 等。
          </p>
        </details>
      </div>
    </section>
  );
}
