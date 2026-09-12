import { Show } from 'solid-js';
import type { IntegrationItem } from '../../types/dashboard';
import { Badge, Button, Card } from '../ui';
import { textOrDash } from '../../lib/format';
import { object } from '../../pages/shared';
import styles from './IntegrationCard.module.scss';

export function IntegrationCard(props: {
  item: IntegrationItem;
  onOpen?: () => void;
  onOpenOfficial?: () => void;
}) {
  const available = () => props.item.active === true || object(props.item.dashboard).available === true;
  return (
    <Card class={styles['integration-card']}>
      <div class={styles['integration-card-head']}>
        <span class="material-icons">extension</span>
        <Badge tone={available() ? 'success' : 'warning'}>{available() ? '可用' : '未安装'}</Badge>
      </div>
      <h3>{textOrDash(props.item.title ?? props.item.name ?? props.item.id)}</h3>
      <p>{textOrDash(props.item.description ?? props.item.role)}</p>
      <div class={styles['integration-card-actions']}>
        <Show when={props.onOpen}><Button icon="open_in_new" disabled={!available()} onClick={props.onOpen}>打开面板</Button></Show>
        <Show when={props.onOpenOfficial}><Button icon="dashboard" disabled={!available()} onClick={props.onOpenOfficial}>官方面板</Button></Show>
      </div>
    </Card>
  );
}
