import {
  createContext, createEffect, createMemo, createSignal, onCleanup, onMount, useContext,
  type Accessor, type JSX, type Setter,
} from 'solid-js';
import { createStore, reconcile, type SetStoreFunction } from 'solid-js/store';
import { api } from '../services/api';
import { parseHash } from '../lib/routing';
import type {
  ConfirmRequest, ConfigSchema, DashboardSnapshot, IntegrationPayload, PageId,
  Theme, ToastMessage, Tone, UnknownRecord,
} from '../types/dashboard';

interface DashboardContextValue {
  page: Accessor<PageId>;
  navigate: (page: PageId) => void;
  theme: Accessor<Theme>;
  toggleTheme: () => void;
  data: DashboardSnapshot;
  setData: SetStoreFunction<DashboardSnapshot>;
  loading: Accessor<boolean>;
  error: Accessor<string>;
  lastUpdated: Accessor<Date | null>;
  refresh: (quiet?: boolean) => Promise<void>;
  schema: Accessor<ConfigSchema | null>;
  config: Accessor<UnknownRecord>;
  configDraft: UnknownRecord;
  setConfigDraft: SetStoreFunction<UnknownRecord>;
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<void>;
  integrations: Accessor<IntegrationPayload | null>;
  loadIntegrations: () => Promise<void>;
  busy: Accessor<boolean>;
  setBusy: Setter<boolean>;
  toasts: Accessor<ToastMessage[]>;
  toast: (message: string, tone?: Tone) => void;
  confirm: (request: ConfirmRequest) => Promise<boolean>;
  confirmRequest: Accessor<(ConfirmRequest & { resolve: (value: boolean) => void }) | null>;
  resolveConfirm: (value: boolean) => void;
  editing: Accessor<boolean>;
  setEditing: Setter<boolean>;
}

const DashboardContext = createContext<DashboardContextValue>();

const unwrapPayload = <T,>(value: T | { data?: T }): T =>
  value && typeof value === 'object' && 'data' in value && (value as { data?: T }).data !== undefined
    ? (value as { data: T }).data
    : value as T;

export function DashboardProvider(props: { children: JSX.Element }) {
  const [page, setPage] = createSignal<PageId>(parseHash());
  const initialTheme = (localStorage.getItem('sl-dashboard-theme') as Theme) || 'light';
  const [theme, setTheme] = createSignal<Theme>(initialTheme);
  const [data, setData] = createStore<DashboardSnapshot>({});
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal('');
  const [lastUpdated, setLastUpdated] = createSignal<Date | null>(null);
  const [schema, setSchema] = createSignal<ConfigSchema | null>(null);
  const [config, setConfig] = createSignal<UnknownRecord>({});
  const [configDraft, setConfigDraft] = createStore<UnknownRecord>({});
  const [integrations, setIntegrations] = createSignal<IntegrationPayload | null>(null);
  const [busy, setBusy] = createSignal(false);
  const [toasts, setToasts] = createSignal<ToastMessage[]>([]);
  const [confirmRequest, setConfirmRequest] =
    createSignal<(ConfirmRequest & { resolve: (value: boolean) => void }) | null>(null);
  const [editing, setEditing] = createSignal(false);
  let toastId = 0;

  const toast = (message: string, tone: Tone = 'default') => {
    const id = ++toastId;
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4200);
  };

  const confirm = (request: ConfirmRequest) =>
    new Promise<boolean>((resolve) => setConfirmRequest({ ...request, resolve }));
  const resolveConfirm = (value: boolean) => {
    const current = confirmRequest();
    if (!current) return;
    setConfirmRequest(null);
    current.resolve(value);
  };

  const refresh = async (quiet = false) => {
    if (loading()) return;
    if (!quiet) setLoading(true);
    setError('');
    try {
      const responses = await Promise.allSettled([
        api.get<UnknownRecord>('/api/metrics'),
        api.get<UnknownRecord>('/api/metrics/trends'),
        api.get<UnknownRecord>('/api/monitoring/health'),
        api.get<UnknownRecord>('/api/monitoring/functions'),
        api.get<UnknownRecord>('/api/persona_updates?limit=10'),
        api.get<UnknownRecord>('/api/style_learning/reviews?limit=5'),
        api.get<UnknownRecord>('/api/jargon/list?page_size=5&confirmed=false&pending=true'),
        api.get<UnknownRecord>('/api/jargon/stats'),
        api.get<UnknownRecord>('/api/persona_management/current?group_id=default'),
        api.get<UnknownRecord>('/api/persona_backups/list?limit=8'),
        api.get<UnknownRecord>('/api/persona_updates/reviewed?limit=5'),
        api.get<UnknownRecord>('/api/data/statistics'),
        api.get<UnknownRecord>('/api/hub/v1/status'),
      ]);
      const value = (index: number) => responses[index].status === 'fulfilled'
        ? unwrapPayload((responses[index] as PromiseFulfilledResult<UnknownRecord>).value)
        : {};
      setData(reconcile({
        metrics: value(0), trends: value(1), health: value(2), functions: value(3),
        persona_updates: value(4),
        style_learning_reviews: value(5),
        jargon_reviews: value(6),
        jargon_stats: value(7), persona_current: value(8), persona_backups: value(9),
        persona_reviewed: value(10), data_statistics: value(11), hub_status: value(12),
      }));
      setLastUpdated(new Date());
      if (responses.every((item) => item.status === 'rejected')) throw new Error('所有 Dashboard 接口均请求失败');
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Dashboard 加载失败';
      setError(message);
      if (!quiet) toast(message, 'danger');
    } finally {
      setLoading(false);
    }
  };

  const loadConfig = async () => {
    try {
      const [schemaPayload, configPayload] = await Promise.all([
        api.get<ConfigSchema | { data?: ConfigSchema }>('/api/config/schema'),
        api.get<UnknownRecord | { data?: UnknownRecord }>('/api/config'),
      ]);
      const nextSchema = unwrapPayload(schemaPayload);
      const nextConfig = unwrapPayload(configPayload);
      setSchema(nextSchema);
      setConfig(nextConfig);
      setConfigDraft(reconcile(structuredClone(nextConfig)));
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : '配置加载失败', 'danger');
    }
  };

  const saveConfig = async () => {
    setBusy(true);
    try {
      const payload = await api.post<UnknownRecord>('/api/config', configDraft);
      const next = objectValue(payload, ['new_config', 'data', 'config']) || structuredClone(configDraft);
      setConfig(next);
      setConfigDraft(reconcile(structuredClone(next)));
      toast('配置已保存', 'success');
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : '配置保存失败', 'danger');
    } finally { setBusy(false); }
  };

  const loadIntegrations = async () => {
    try {
      const payload = await api.get<IntegrationPayload | { data?: IntegrationPayload }>('/api/integrations/status');
      setIntegrations(unwrapPayload(payload));
    } catch (caught) {
      toast(caught instanceof Error ? caught.message : '融合状态加载失败', 'danger');
    }
  };

  const navigate = (next: PageId) => {
    if (page() === next) return;
    window.location.hash = `#/${next}`;
    setPage(next);
    window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };

  createEffect(() => {
    document.documentElement.dataset.theme = theme();
    localStorage.setItem('sl-dashboard-theme', theme());
  });
  onMount(() => {
    const hashHandler = () => setPage(parseHash());
    window.addEventListener('hashchange', hashHandler);
    refresh();
    loadConfig();
    loadIntegrations();
    const timer = window.setInterval(() => {
      if (!editing() && !busy()) refresh(true);
    }, 60_000);
    onCleanup(() => {
      window.removeEventListener('hashchange', hashHandler);
      window.clearInterval(timer);
    });
  });

  const value = createMemo<DashboardContextValue>(() => ({
    page, navigate, theme, toggleTheme: () => setTheme((current) => current === 'light' ? 'dark' : 'light'),
    data, setData, loading, error, lastUpdated, refresh, schema, config, configDraft,
    setConfigDraft, loadConfig, saveConfig, integrations, loadIntegrations, busy, setBusy,
    toasts, toast, confirm, confirmRequest, resolveConfirm, editing, setEditing,
  }));
  return <DashboardContext.Provider value={value()}>{props.children}</DashboardContext.Provider>;
}

function objectValue(payload: UnknownRecord, keys: string[]): UnknownRecord | null {
  for (const key of keys) {
    const value = payload[key];
    if (value && typeof value === 'object' && !Array.isArray(value)) return value as UnknownRecord;
  }
  return Object.keys(payload).length ? payload : null;
}

export function useDashboard(): DashboardContextValue {
  const context = useContext(DashboardContext);
  if (!context) throw new Error('useDashboard must be used inside DashboardProvider');
  return context;
}
