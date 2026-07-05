import { Show, type JSX } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { Button } from '../ui';
import styles from './PageHeader.module.scss';

export function PageHeader(props: { title: string; description: string; icon?: string; actions?: JSX.Element; home?: boolean }) {
  const dashboard = useDashboard();
  return (
    <header class={styles['page-header']}>
      <div class={styles['page-header-heading']}>
        <Show when={!props.home}>
          <Button class={styles['page-back-button']} icon="arrow_back_ios" title="返回上一级页面"
            onClick={() => dashboard.navigate('home')}></Button>
        </Show>
        <div>
          <h2>{props.title}</h2>
          <p>{props.description}</p>
        </div>
      </div>
      <div class={styles['page-header-actions']}>
        {props.actions}
      </div>
    </header>
  );
}
