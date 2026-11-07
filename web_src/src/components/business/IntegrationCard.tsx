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
  const devApi = () => object(props.item.dev_api);
  const active = () => props.item.active === true || dash().available === true;
  // 有可用面板入口（外部链接、官方面板或内部路由）才允许点击，避免"可点但无动作"
  const actionable = () =>
    dash().available === true
    || String(dash().route ?? '').startsWith('#/')
    || Boolean(dash().external_url)
    || Boolean(dash().official_page_url);
  const healthy = (): boolean | null => {
    const value = status().healthy;
    return typeof value === 'boolean' ? value : null;
  };
  // 状态徽标：正常 / 异常 / 未知 / 未安装（与内嵌页 integrationStatusBadge 同口径）
  const badge = () => healthy() === true ? '正常' : healthy() === false ? '异常' : active() ? '未知' : '未安装';
  const tone = () => healthy() === true ? 'success' : healthy() === false ? 'danger' : 'warning';
  // 委托状态独立成徽标，不掩盖健康状态（内嵌页既有信息移植）
  const delegated = (): boolean | null => {
    const value = props.item.delegated;
    return typeof value === 'boolean' ? value : null;
  };
  return (
    <Card class={styles['integration-card']}>
      <div class={styles['integration-card-head']}>
        <h3>{textOrDash(props.item.title ?? props.item.name ?? props.item.id)}</h3>
        <div class={styles['integration-badges']}>
          <Badge tone={tone()}>{badge()}</Badge>
          <Show when={delegated() !== null}>
            <Badge tone={delegated() ? 'success' : 'default'}>{delegated() ? '已委托' : '未委托'}</Badge>
          </Show>
        </div>
      </div>
      <p>{textOrDash(props.item.description ?? props.item.role)}</p>
      <Show when={String(status().message ?? '')}>
        <p class={styles['integration-card-status']}>{String(status().message)}</p>
      </Show>
      <Show when={String(devApi().mode ?? '')}>
        <p class={styles['integration-card-status']}>{String(devApi().mode)}</p>
      </Show>
      <div class={styles['integration-card-actions']}>
        <Show when={props.onOpen}><Button icon="open_in_new" disabled={!actionable()} onClick={props.onOpen}>打开面板</Button></Show>
      </div>
    </Card>
  );
}
