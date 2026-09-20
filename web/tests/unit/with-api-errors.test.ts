import { describe, expect, it, vi } from 'vitest';
import { withApiErrors, NO_STORE } from '@/lib/api/with-api-errors';
import { ByokRequiredError } from '@/lib/llm/errors';

describe('withApiErrors', () => {
  it('returns the handler response on success', async () => {
    const handler = vi.fn().mockResolvedValue(new Response('{"ok":true}'));
    const wrapped = withApiErrors(handler, () => 'test');
    const response = await wrapped();
    expect(response.status).toBe(200);
    expect(handler).toHaveBeenCalledOnce();
  });

  it('converts AppError to the JSON contract with no-store headers', async () => {
    const handler = vi.fn().mockRejectedValue(new ByokRequiredError());
    const wrapped = withApiErrors(handler, () => 'test');
    const response = await wrapped();
    expect(response.status).toBe(401);
    expect(response.headers.get('Cache-Control')).toBe(NO_STORE['Cache-Control']);
    const body = (await response.json()) as { error: string; message: string };
    expect(body.error).toBe('byok_required');
    expect(body.message).toContain('Add an API key');
  });

  it('maps unknown errors to 500 internal', async () => {
    const handler = vi.fn().mockRejectedValue(new Error('mystery'));
    const wrapped = withApiErrors(handler, () => 'test');
    const response = await wrapped();
    expect(response.status).toBe(500);
    const body = (await response.json()) as { error: string };
    expect(body.error).toBe('internal');
  });
});
