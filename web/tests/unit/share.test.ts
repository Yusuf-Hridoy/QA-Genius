import { describe, expect, it } from 'vitest';
import { deflateSync, strToU8 } from 'fflate';
import {
  MAX_BYTES,
  MAX_INFLATED_BYTES,
  WARN_BYTES,
  decodeShare,
  encodeShare,
  formatKilobytes,
  fragmentBytes,
  stripRunForShare,
  ShareDecodeError,
} from '@/lib/share/codec';
import { newRun } from '@/lib/store/run';
import type { Run } from '@/lib/pipeline/types';

/** Minimal fragment encoder for hostile payloads (mirrors the codec). */
function toFragment(payload: Record<string, unknown>): string {
  const bytes = deflateSync(strToU8(JSON.stringify(payload)));
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i] as number);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function sampleRun(): Run {
  const run = newRun('Aurora Storefront');
  run.story = {
    input: {
      user_story: 'As a shopper, I want to save items for later so I can buy them next visit.',
      story_type: 'User Story',
    },
    output: {
      ambiguity_score: 20,
      clarity_label: 'Crystal Clear',
      invest_overall: 'PASS',
      invest_independent: 'PASS',
      invest_negotiable: 'PASS',
      invest_valuable: 'PASS',
      invest_estimable: 'PASS',
      invest_small: 'PASS',
      invest_testable: 'PASS',
      vague_phrases: [],
      missing_elements: [],
      suggested_rewrites: [],
      generated_acceptance_criteria: ['AC one'],
      risks: [],
    },
    meta: { provider: 'gemini', model: 'gemini-2.5-flash-lite', requestId: 'secret-id' },
  };
  return run;
}

describe('share codec', () => {
  it('round-trips a run through encode and decode', () => {
    const run = sampleRun();
    const fragment = encodeShare(run, { name: 'Aurora Storefront', stack: 'Next.js' });
    const payload = decodeShare(fragment);
    expect(payload.v).toBe(1);
    expect(payload.kind).toBe('run');
    expect(payload.project.name).toBe('Aurora Storefront');
    expect((payload.run as Run).id).toBe(run.id);
  });

  it('strips meta (provider, model, request id) before encoding', () => {
    const stripped = stripRunForShare(sampleRun());
    expect(JSON.stringify(stripped)).not.toContain('gemini');
    expect(JSON.stringify(stripped)).not.toContain('secret-id');
    // The payload itself is intact.
    const story = stripped.story as { output?: { clarity_label?: string } };
    expect(story.output?.clarity_label).toBe('Crystal Clear');
  });

  it('rejects invalid base64 and wrong versions', () => {
    expect(() => decodeShare('!!!not-valid!!!')).toThrow(ShareDecodeError);
    expect(() => decodeShare('')).toThrow(ShareDecodeError);
    // Wrong version envelope encoded directly.
    const bad = btoa(JSON.stringify({ v: 2, kind: 'run', run: {}, project: {} }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_');
    expect(() => decodeShare(bad)).toThrow(ShareDecodeError);
  });

  it('computes sizes against the warn and max budgets', () => {
    const fragment = encodeShare(sampleRun(), { name: 'Aurora Storefront', stack: 'Next.js' });
    expect(fragmentBytes(fragment)).toBeGreaterThan(0);
    expect(fragmentBytes(fragment)).toBeLessThan(WARN_BYTES);
    expect(MAX_BYTES).toBeGreaterThan(WARN_BYTES);
    expect(formatKilobytes(14 * 1024)).toBe('14 KB');
  });

  it('rejects a malformed run payload', () => {
    const project = { name: 'Aurora Storefront', stack: 'Next.js' };
    // Run id must be a string.
    expect(() => decodeShare(toFragment({ v: 1, kind: 'run', run: { id: 42 }, project }))).toThrow(
      ShareDecodeError,
    );
    // Test-case output must match the generator schema.
    expect(() =>
      decodeShare(
        toFragment({
          v: 1,
          kind: 'run',
          run: {
            id: 'run-1',
            createdAt: '2026-09-20T00:00:00.000Z',
            updatedAt: '2026-09-20T00:00:00.000Z',
            projectName: 'Aurora Storefront',
            testCases: {
              input: {
                user_story:
                  'As a shopper, I want cart quantity limits so the warehouse can fulfil orders.',
              },
              output: { nonsense: true },
            },
          },
          project,
        }),
      ),
    ).toThrow(ShareDecodeError);
  });

  it('rejects an inflated payload over 2 MB', () => {
    // Highly compressible: tiny fragment, huge inflated output.
    const bytes = deflateSync(strToU8('x'.repeat(MAX_INFLATED_BYTES + 1)));
    let binary = '';
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i] as number);
    const fragment = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    expect(fragmentBytes(fragment)).toBeLessThan(MAX_BYTES);
    expect(() => decodeShare(fragment)).toThrow(ShareDecodeError);
  });
});
