import { describe, expect, it, vi } from 'vitest';

const inflateSpy = vi.hoisted(() => vi.fn());

vi.mock('fflate', async (importOriginal) => {
  const actual = await importOriginal<typeof import('fflate')>();
  return {
    ...actual,
    inflateSync: (...args: unknown[]) => {
      inflateSpy(...args);
      return (actual.inflateSync as (...a: never[]) => Uint8Array)(...(args as never[]));
    },
  };
});

import { deflateSync, strToU8 } from 'fflate';
import { MAX_INFLATED_BYTES, ShareDecodeError, decodeShare, encodeShare } from '@/lib/share/codec';
import { newRun } from '@/lib/store/run';

function toFragment(payload: Record<string, unknown>): string {
  const bytes = deflateSync(strToU8(JSON.stringify(payload)));
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i] as number);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

describe('share inflate cap', () => {
  it('passes a bounded out buffer to inflateSync', () => {
    inflateSpy.mockClear();
    const run = newRun('Aurora Storefront');
    const fragment = encodeShare(run, { name: 'Aurora Storefront', stack: 'Next.js' });
    decodeShare(fragment);
    expect(inflateSpy).toHaveBeenCalledOnce();
    const options = inflateSpy.mock.calls[0]?.[1] as { out?: Uint8Array } | undefined;
    expect(options?.out).toBeInstanceOf(Uint8Array);
    // +1 so an overshoot is detectable; never an unbounded allocation.
    expect(options?.out?.length).toBe(MAX_INFLATED_BYTES + 1);
  });

  it('fails an oversized payload without allocating beyond the cap', () => {
    inflateSpy.mockClear();
    const bytes = deflateSync(strToU8('x'.repeat(MAX_INFLATED_BYTES + 1)));
    let binary = '';
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i] as number);
    const fragment = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    expect(() => decodeShare(fragment)).toThrow(ShareDecodeError);
    expect(inflateSpy).toHaveBeenCalledOnce();
    const options = inflateSpy.mock.calls[0]?.[1] as { out?: Uint8Array } | undefined;
    expect(options?.out?.length).toBeLessThanOrEqual(MAX_INFLATED_BYTES + 1);
  });

  it('rejects a wrong-version envelope', () => {
    expect(() => decodeShare(toFragment({ v: 2, kind: 'run' }))).toThrow(ShareDecodeError);
  });
});
