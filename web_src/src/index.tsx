/* @refresh reload */
import './styles/main.scss';

import { render } from 'solid-js/web';

import { App } from './app/App';
import { applyCustomCss, loadCustomCss } from './lib/customStyle';

const root = document.getElementById('root');

if (import.meta.env.DEV && !(root instanceof HTMLElement)) {
  throw new Error(
    'Root element not found. Did you forget to add it to your index.html? Or maybe the id attribute got misspelled?',
  );
}

// 在首次渲染前注入用户自定义 CSS，避免默认风格闪烁
applyCustomCss(loadCustomCss());

render(() => <App />, root!);
