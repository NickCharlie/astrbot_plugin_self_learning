// 审查记录的变更预览解析。
// 后端把 before/after 人格快照放在 change_preview（待审）或 change_snapshot
// （已审）里；部分旧接口直接把 original_content/new_content 放在顶层。
// ReviewCard 需要兼容这些来源，否则「查看变更详情」会因为没有 before/after
// 而整块不渲染（issue #280）。
import type { ReviewItem, UnknownRecord } from '../types/dashboard';

const asRecord = (value: unknown): UnknownRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};

const asText = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  return typeof value === 'string' ? value : String(value);
};

const asList = (value: unknown): unknown[] => Array.isArray(value) ? value : [];

/** 优先读取后端统一的变更预览载荷。 */
export const reviewChangePreview = (item: ReviewItem | UnknownRecord): UnknownRecord =>
  asRecord(
    item.change_preview
    ?? item.persona_change_preview
    ?? item.change_snapshot
    ?? item.persona_change_snapshot,
  );

/** 变更前的 system_prompt。 */
export const reviewBeforePrompt = (item: ReviewItem | UnknownRecord): string => {
  const preview = reviewChangePreview(item);
  return asText(
    preview.before_system_prompt
    ?? item.before_system_prompt
    ?? item.before
    ?? item.original_content
    ?? item.original_prompt,
  );
};

/** 变更后的 system_prompt。 */
export const reviewAfterPrompt = (item: ReviewItem | UnknownRecord): string => {
  const preview = reviewChangePreview(item);
  return asText(
    preview.after_system_prompt
    ?? item.after_system_prompt
    ?? item.after
    ?? item.new_content
    ?? item.proposed_content
    ?? preview.proposed_content
    // 部分旧记录只把待审文本放在 content 中（原 ReviewCard 的兜底行为）
    ?? item.content,
  );
};

/** begin_dialogs 的 before/after。 */
export const reviewBeginDialogs = (item: ReviewItem | UnknownRecord): { before: unknown[]; after: unknown[] } => {
  const preview = reviewChangePreview(item);
  return {
    before: asList(preview.before_begin_dialogs ?? item.before_begin_dialogs),
    after: asList(preview.after_begin_dialogs ?? item.after_begin_dialogs),
  };
};

/** 把示例对话列表转成可逐行 diff 的文本。 */
export const formatDialogLines = (dialogs: unknown[]): string =>
  dialogs
    .map((dialog) => typeof dialog === 'string' ? dialog : JSON.stringify(dialog))
    .filter((line) => line.length > 0)
    .join('\n');

/** 变更元信息（应用方式、目标字段、来源群组）。 */
export const reviewChangeMeta = (item: ReviewItem | UnknownRecord): string[] => {
  const preview = reviewChangePreview(item);
  const meta: string[] = [];
  const mode = asText(preview.application_mode);
  if (mode) meta.push(`应用方式：${mode}`);
  const fields = asList(preview.target_fields ?? preview.affected_fields).map(asText).filter(Boolean);
  if (fields.length) meta.push(`影响字段：${fields.join('、')}`);
  const groupId = asText(preview.group_id ?? item.group_id);
  if (groupId) meta.push(`群组：${groupId}`);
  const proposed = asText(preview.proposed_content);
  if (proposed) meta.push(`建议内容：${proposed.length} 字`);
  return meta;
};

/** 本次审查是否有可展示的变更内容。 */
export const reviewHasChange = (item: ReviewItem | UnknownRecord): boolean => {
  if (reviewBeforePrompt(item) || reviewAfterPrompt(item)) return true;
  const dialogs = reviewBeginDialogs(item);
  return dialogs.before.length > 0 || dialogs.after.length > 0;
};
