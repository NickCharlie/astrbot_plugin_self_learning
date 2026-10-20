import { Show } from 'solid-js';
import type { IntegrationItem } from '../../types/dashboard';
import { Badge, Button, Card } from '../ui';
import { textOrDash } from '../../lib/format';
import { object } from '../../pages/shared';
import styles from './IntegrationCard.module.scss';

export function IntegrationCard(props: {
  item: IntegrationItem;
  onOpen?: () => void;
}) {
  const status = () => object(props.item.status);
  const dash = () => object(props.item.dashboard);
  const active = () => props.item.active === true || dash().available === true;
  // 有可用面板入口（外部链接或内部路由）才允许点击，避免"可点但无动作"
  const actionable = () =>
    dash().available === true || String(dash().route ?? '').startsWith('#/');
  const healthy = (): boolean | null => {
    const value = status().healthy;
    return typeof value === 'boolean' ? value : null;
  };
  const badge = () => healthy() === true ? '正常' : healthy() === false ? '异常' : active() ? '未知' : '未安装';
  const tone = () => healthy() === true ? 'success' : healthy() === false ? 'danger' : 'warning';
  return (
    <Card class={styles['integration-card']}>
      <div class={styles['integration-card-head']}>
        <span class="material-icons">extension</span>
        <Badge tone={tone()}>{badge()}</Badge>
      </div>
      <h3>{textOrDash(props.item.title ?? props.item.name ?? props.item.id)}</h3>
      <p>{textOrDash(props.item.description ?? props.item.role)}</p>
      <Show when={String(status().message ?? '')}>
        <p class={styles['integration-card-status']}>{String(status().message)}</p>
      </Show>
      <div class={styles['integration-card-actions']}>
        <Show when={props.onOpen}><Button icon="open_in_new" disabled={!actionable()} onClick={props.onOpen}>打开面板</Button></Show>
      </div>
    </Card>
  );
}
