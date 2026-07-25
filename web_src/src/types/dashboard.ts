export type PageId =
  | 'home' | 'overview' | 'insights' | 'monitoring' | 'reviews'
  | 'jargon-learning' | 'expression-learning' | 'persona-learning'
  | 'shadow-mode' | 'content' | 'reply-strategy' | 'graphs' | 'integrations' | 'settings';

export type Theme = 'light' | 'dark';
export type Tone = 'default' | 'primary' | 'success' | 'warning' | 'danger';
export type UnknownRecord = Record<string, unknown>;

export interface DashboardSnapshot extends UnknownRecord {
  metrics?: UnknownRecord;
  health?: UnknownRecord;
  learning?: UnknownRecord;
  trends?: UnknownRecord;
  persona_updates?: ReviewItem[] | UnknownRecord;
  style_learning_reviews?: ReviewItem[] | UnknownRecord;
  jargon_reviews?: JargonItem[] | UnknownRecord;
}

export interface ReviewItem extends UnknownRecord {
  id?: string | number;
  title?: string;
  status?: string;
  created_at?: string | number;
  review_source?: string;
  content?: string;
  pattern_details?: unknown;
  few_shot_pairs?: unknown;
}

export interface JargonItem extends UnknownRecord {
  id?: string | number;
  content?: string;
  jargon?: string;
  meaning?: string;
  definition?: string;
  is_confirmed?: boolean;
  status?: string;
  created_at?: string | number;
}

export interface Paginated<T> extends UnknownRecord {
  items?: T[];
  data?: T[];
  total?: number;
  page?: number;
  page_size?: number;
}

export interface ConfigField extends UnknownRecord {
  key: string;
  label?: string;
  description?: string;
  type?: string;
  widget?: string;
  options?: Array<{ label?: string; value: unknown } | string | number>;
  default?: unknown;
  min?: number;
  max?: number;
  provider_type?: string;
  provider_type_label?: string;
}

export interface ConfigGroup extends UnknownRecord {
  key?: string;
  name?: string;
  label?: string;
  description?: string;
  fields?: ConfigField[];
}

export interface ConfigSchema extends UnknownRecord {
  groups?: ConfigGroup[];
  fields?: ConfigField[];
  warnings?: Array<string | UnknownRecord>;
  provider_options_by_type?: Record<string, unknown[]>;
}

export interface GraphNode extends UnknownRecord {
  id?: string | number;
  name?: string;
  label?: string;
  value?: number;
  category?: string | number;
}

export interface GraphLink extends UnknownRecord {
  source: string | number;
  target: string | number;
  value?: number;
}

export interface GraphPayload extends UnknownRecord {
  nodes?: GraphNode[];
  links?: GraphLink[];
  edges?: GraphLink[];
  categories?: UnknownRecord[];
}

export interface IntegrationItem extends UnknownRecord {
  id?: string;
  title?: string;
  name?: string;
  description?: string;
  available?: boolean;
  enabled?: boolean;
  dashboard?: UnknownRecord;
}

export interface IntegrationPayload extends UnknownRecord {
  dashboards?: IntegrationItem[];
  integrations?: IntegrationItem[];
  items?: IntegrationItem[];
  delegation?: UnknownRecord;
  hub?: UnknownRecord;
  warnings?: unknown[];
}

export interface ToastMessage {
  id: number;
  message: string;
  tone: Tone;
}

export interface ConfirmRequest {
  title: string;
  message: string;
  confirmText?: string;
  tone?: Tone;
}
