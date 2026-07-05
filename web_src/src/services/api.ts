export class ApiError extends Error {
  constructor(message: string, public status: number, public payload?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

const errorMessage = (payload: unknown, status: number): string => {
  if (payload && typeof payload === 'object') {
    const object = payload as Record<string, unknown>;
    for (const key of ['error', 'message', 'detail']) {
      if (typeof object[key] === 'string' && object[key]) return object[key] as string;
    }
  }
  return `请求失败（HTTP ${status}）`;
};

export async function requestJson<T>(
  url: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...init,
    signal: signal ?? init.signal,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) throw new ApiError(errorMessage(payload, response.status), response.status, payload);
  return payload as T;
}

export const api = {
  get: <T>(url: string, signal?: AbortSignal) => requestJson<T>(url, {}, signal),
  post: <T>(url: string, body: unknown, signal?: AbortSignal) =>
    requestJson<T>(url, { method: 'POST', body: JSON.stringify(body) }, signal),
  put: <T>(url: string, body: unknown, signal?: AbortSignal) =>
    requestJson<T>(url, { method: 'PUT', body: JSON.stringify(body) }, signal),
  delete: <T>(url: string, signal?: AbortSignal) =>
    requestJson<T>(url, { method: 'DELETE' }, signal),
};

export function abortable() {
  const controller = new AbortController();
  return { signal: controller.signal, abort: () => controller.abort() };
}
