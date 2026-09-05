/** 整页导航助手：独立成模块便于单测中 mock，避免 jsdom 真实跳转。 */
export function replaceLocation(url: string): void {
  window.location.replace(url);
}
