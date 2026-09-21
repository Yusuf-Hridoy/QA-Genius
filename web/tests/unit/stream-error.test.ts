import { describe, expect, it } from 'vitest';
import {
  STREAM_ERROR_KEY,
  STREAM_ERROR_SENTINEL,
  decodeStreamError,
  encodeStreamError,
} from '@/lib/llm/stream-error';

describe('stream error sentinel', () => {
  it('round-trips code and message', () => {
    const line = encodeStreamError('provider_rate_limited', 'Slow down.');
    expect(line.startsWith(STREAM_ERROR_SENTINEL)).toBe(true);
    expect(line).toContain(STREAM_ERROR_KEY);
    const split = decodeStreamError(`{"ok":true}${line}`);
    expect(split.jsonText).toBe('{"ok":true}');
    expect(split.code).toBe('provider_rate_limited');
    expect(split.message).toBe('Slow down.');
  });

  it('returns the input untouched when no sentinel is present', () => {
    expect(decodeStreamError('{"ok":true}')).toEqual({ jsonText: '{"ok":true}' });
  });

  it('maps a malformed sentinel to provider_unavailable', () => {
    const split = decodeStreamError(`{"ok":true}${STREAM_ERROR_SENTINEL}not-json`);
    expect(split.jsonText).toBe('{"ok":true}');
    expect(split.code).toBe('provider_unavailable');
  });
});
