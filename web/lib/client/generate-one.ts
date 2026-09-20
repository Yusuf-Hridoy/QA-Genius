'use client';

import { parsePartialJson } from './parse-partial-json';
import type { StreamMeta } from './use-object-stream';

/**
 * Single-shot POST through an /api/generate/[kind] route: consumes the
 * partial-JSON stream to the final object and returns it with the response
 * meta. Used by flows that need the whole object at once (duel, refine)
 * instead of progressive rendering.
 */
export async function generateOne(
  kind: string,
  body: unknown,
  headers: Record<string, string>,
): Promise<{ data: unknown; meta: StreamMeta }> {
  const response = await fetch(`/api/generate/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
  const meta: StreamMeta = {
    provider: response.headers.get('x-qag-provider') ?? undefined,
    model: response.headers.get('x-qag-model') ?? undefined,
    tier: response.headers.get('x-qag-tier') ?? undefined,
    requestId: response.headers.get('x-qag-request-id') ?? undefined,
    repaired: response.headers.get('x-qag-repaired') === '1',
    suspicious: response.headers.get('x-qag-suspicious') === '1',
  };
  if (!response.ok || !response.body) {
    const data: unknown = await response.json().catch(() => null);
    const parsed = data && typeof data === 'object' ? (data as { message?: string }) : {};
    throw new Error(parsed.message ?? 'The request failed. Try again.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let accumulated = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    accumulated += decoder.decode(value, { stream: true });
  }
  const data = parsePartialJson(accumulated);
  if (data === undefined) {
    throw new Error('The model returned output that could not be read. Try again.');
  }
  return { data, meta };
}
