/**
 * 用户自定义 CSS：localStorage 持久化，启动时注入 <style id="slx-custom-style">。
 * 面板里的样式钩子均使用独一无二的 slx- 前缀，见 CustomStylePanel 的钩子清单。
 */
const STORAGE_KEY = 'sl-custom-css';
const THEME_STORAGE_KEY = 'sl-dashboard-theme';
export const CUSTOM_STYLE_ELEMENT_ID = 'slx-custom-style';

export function loadCustomCss(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

/** 应用自定义 CSS：空串视为清除；非空写入注入的 style 标签并持久化。 */
export function applyCustomCss(css: string): void {
  const content = css ?? '';
  const existing = document.getElementById(CUSTOM_STYLE_ELEMENT_ID);
  if (!content.trim()) {
    existing?.remove();
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* 存储不可用时忽略 */
    }
    return;
  }
  let element = existing as HTMLStyleElement | null;
  if (!element) {
    element = document.createElement('style');
    element.id = CUSTOM_STYLE_ELEMENT_ID;
    document.head.appendChild(element);
  }
  element.textContent = content;
  try {
    localStorage.setItem(STORAGE_KEY, content);
  } catch {
    /* 存储不可用时仅本次会话生效 */
  }
}

/** 重置默认风格：清除自定义 CSS 与主题覆盖，页面刷新后完全回到默认。 */
export function resetCustomStyle(): void {
  applyCustomCss('');
  try {
    localStorage.removeItem(THEME_STORAGE_KEY);
  } catch {
    /* 存储不可用时忽略 */
  }
}
