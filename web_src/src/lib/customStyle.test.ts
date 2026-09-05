import { beforeEach, describe, expect, it } from 'vitest';
import {
  CUSTOM_STYLE_ELEMENT_ID,
  applyCustomCss,
  loadCustomCss,
  resetCustomStyle,
} from './customStyle';

describe('customStyle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.getElementById(CUSTOM_STYLE_ELEMENT_ID)?.remove();
  });

  it('injects and persists custom css', () => {
    applyCustomCss('.slx-panel { border-radius: 0; }');

    const element = document.getElementById(CUSTOM_STYLE_ELEMENT_ID) as HTMLStyleElement;
    expect(element).toBeTruthy();
    expect(element.textContent).toContain('.slx-panel');
    expect(loadCustomCss()).toContain('.slx-panel');
  });

  it('reuses the same style element across applies', () => {
    applyCustomCss('a{}');
    applyCustomCss('b{}');

    expect(document.querySelectorAll(`#${CUSTOM_STYLE_ELEMENT_ID}`)).toHaveLength(1);
    expect(document.getElementById(CUSTOM_STYLE_ELEMENT_ID)!.textContent).toBe('b{}');
  });

  it('removes the style element when css is cleared', () => {
    applyCustomCss('a{}');
    applyCustomCss('   ');

    expect(document.getElementById(CUSTOM_STYLE_ELEMENT_ID)).toBeNull();
    expect(loadCustomCss()).toBe('');
  });

  it('resetCustomStyle clears css and theme override', () => {
    localStorage.setItem('sl-dashboard-theme', 'dark');
    applyCustomCss('a{}');

    resetCustomStyle();

    expect(loadCustomCss()).toBe('');
    expect(localStorage.getItem('sl-dashboard-theme')).toBeNull();
    expect(document.getElementById(CUSTOM_STYLE_ELEMENT_ID)).toBeNull();
  });
});
