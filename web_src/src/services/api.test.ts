import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestJson } from './api';

describe('requestJson', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns parsed json', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"ok":true}', { status: 200 }));
    await expect(requestJson<{ ok: boolean }>('/ok')).resolves.toEqual({ ok: true });
  });

  it('extracts backend errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"error":"bad"}', { status: 400 }));
    await expect(requestJson('/bad')).rejects.toEqual(expect.objectContaining({ message: 'bad', status: 400 }));
  });
});
