import { createSignal, Show } from 'solid-js';
import { useDashboard } from '../../stores/dashboard';
import { PageHeader } from '../../components/layout/PageHeader';
import { Button, EmptyState, Panel } from '../../components/ui';
import styles from './ReplyStrategyPage.module.scss';

export function ReplyStrategyPage() {
  const dashboard = useDashboard();
  const [loaded, setLoaded] = createSignal(false);
  const [key, setKey] = createSignal(0);
  const reload = () => { setLoaded(false); setKey((value) => value + 1); };
  return (
    <div class="page">
      <PageHeader title="回复策略" description="在当前 Dashboard 中嵌入 Group Chat Plus 的策略面板。" icon="quickreply" />
      <Panel title="Group Chat Plus" hint="面板按需加载，未安装配套插件时会显示后端错误页。" actions={<Button icon="refresh" onClick={reload}>重新加载</Button>}>
        <div class={styles['companion-frame-shell']}>
          <Show when={!loaded()}><EmptyState icon="hourglass_top" title="正在加载配套面板" /></Show>
          <iframe
            title="Group Chat Plus 面板"
            src={`/api/integrations/embed/group_chat_plus?reload=${key()}`}
            onLoad={() => setLoaded(true)}
          />
        </div>
        <p class="footer-note">若浏览器阻止嵌入，可在“功能融合”页面查看插件状态或打开独立面板。</p>
      </Panel>
    </div>
  );
}
