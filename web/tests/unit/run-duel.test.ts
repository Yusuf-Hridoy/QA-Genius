import { afterEach, describe, expect, it, vi } from 'vitest';
import { generateOne } from '@/lib/client/generate-one';
import { runDuel } from '@/lib/duel/run-duel';
import sampleA from '../../fixtures/story_interpretation/sample-a.json';
import sampleB from '../../fixtures/story_interpretation/sample-b.json';
import duelOutput from '../../fixtures/duel_compare/sample-output.json';

function streamResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'x-qag-provider': 'gemini',
      'x-qag-model': 'gemini-2.5-flash-lite',
      'x-qag-tier': 'fast',
      'x-qag-request-id': 'unit-request-1',
      'Cache-Control': 'no-store',
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('generateOne', () => {
  it('returns the final object with response meta', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse({ ok: true })));
    const { data, meta } = await generateOne('ping', {}, { 'x-llm-provider': 'gemini' });
    expect(data).toEqual({ ok: true });
    expect(meta.provider).toBe('gemini');
    expect(meta.requestId).toBe('unit-request-1');
  });

  it('throws the server message on error status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: 'byok_required', message: 'Add a key.' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    await expect(generateOne('ping', {}, {})).rejects.toThrow('Add a key.');
  });
});

describe('runDuel', () => {
  it('posts A and B in parallel, then compares, with deterministic additions', async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init: { body: string }) => {
        seen.push(url);
        const body = JSON.parse(init.body) as { persona?: string };
        if (url.endsWith('/story_interpretation')) {
          return Promise.resolve(streamResponse(body.persona === 'B' ? sampleB : sampleA));
        }
        return Promise.resolve(streamResponse(duelOutput));
      }),
    );
    const stages: Array<[string, boolean]> = [];
    const duel = await runDuel({
      userStory:
        'As a shopper, I want my account to lock after several failed login attempts so that my account stays secure, and it may unlock after some time or stay locked until I reset my password.',
      headers: {},
      onStage: (stage, done) => stages.push([stage, done]),
    });
    expect(seen.filter((u) => u.endsWith('/story_interpretation'))).toHaveLength(2);
    expect(seen.filter((u) => u.endsWith('/duel_compare'))).toHaveLength(1);
    expect(duel.forks).toHaveLength(3);
    expect(duel.agreementRatio).toBeCloseTo(2 / 5);
    expect(duel.highlights).toHaveLength(3);
    expect(stages).toContainEqual(['A', true]);
    expect(stages).toContainEqual(['B', true]);
    expect(stages).toContainEqual(['compare', true]);
  });
});
