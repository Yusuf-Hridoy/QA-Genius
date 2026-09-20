import { describe, expect, it } from 'vitest';
import { buildByokHeaders, parseByok } from '@/lib/llm/byok';
import { ByokRequiredError, UnsupportedProviderError } from '@/lib/llm/errors';
import type { StoredKey } from '@/lib/store/keys';

function headers(entries: Record<string, string>): Headers {
  return new Headers(entries);
}

describe('parseByok', () => {
  it('parses valid headers', () => {
    const byok = parseByok(
      headers({ 'x-llm-provider': 'gemini', 'x-llm-key': 'abc123', 'x-llm-tier': 'reasoning' }),
    );
    expect(byok).toEqual({ provider: 'gemini', apiKey: 'abc123', tier: 'reasoning' });
  });

  it('defaults the tier to fast', () => {
    const byok = parseByok(headers({ 'x-llm-provider': 'groq', 'x-llm-key': 'abc123' }));
    expect(byok.tier).toBe('fast');
  });

  it('throws byok_required when headers are missing', () => {
    expect(() => parseByok(headers({}))).toThrow(ByokRequiredError);
    expect(() => parseByok(headers({ 'x-llm-provider': 'gemini' }))).toThrow(ByokRequiredError);
  });

  it('throws unsupported_provider for an unknown provider', () => {
    expect(() => parseByok(headers({ 'x-llm-provider': 'acme', 'x-llm-key': 'abc123' }))).toThrow(
      UnsupportedProviderError,
    );
  });

  it('rejects keys over 512 chars', () => {
    expect(() =>
      parseByok(headers({ 'x-llm-provider': 'gemini', 'x-llm-key': 'a'.repeat(513) })),
    ).toThrow(ByokRequiredError);
  });

  it('rejects non-printable key characters', () => {
    // The Headers class strips newlines from values, so use a bare stub here.
    const stub = {
      get: (name: string) => ({ 'x-llm-provider': 'gemini', 'x-llm-key': 'ab\tcd' })[name] ?? null,
    } as Headers;
    expect(() => parseByok(stub)).toThrow(ByokRequiredError);
  });

  it('requires a base URL only for openai-compatible', () => {
    expect(() =>
      parseByok(headers({ 'x-llm-provider': 'openai-compatible', 'x-llm-key': 'k' })),
    ).toThrow(UnsupportedProviderError);

    const byok = parseByok(
      headers({
        'x-llm-provider': 'openai-compatible',
        'x-llm-key': 'k',
        'x-llm-base-url': 'http://localhost:11434/v1',
      }),
    );
    expect(byok.baseUrl).toBe('http://localhost:11434/v1');
  });

  it('rejects a base URL without http(s)://', () => {
    expect(() =>
      parseByok(
        headers({
          'x-llm-provider': 'openai-compatible',
          'x-llm-key': 'k',
          'x-llm-base-url': 'localhost:11434/v1',
        }),
      ),
    ).toThrow(UnsupportedProviderError);
  });

  it('passes through model override', () => {
    const byok = parseByok(
      headers({
        'x-llm-provider': 'openai',
        'x-llm-key': 'k',
        'x-llm-model': 'gpt-4o',
      }),
    );
    expect(byok.model).toBe('gpt-4o');
  });
});

describe('buildByokHeaders', () => {
  const key: StoredKey = {
    id: '1',
    provider: 'gemini',
    label: 'Gemini',
    apiKey: 'secret-key-value',
    createdAt: new Date().toISOString(),
  };

  it('builds headers for a stored key', () => {
    expect(buildByokHeaders(key, 'fast')).toEqual({
      'x-llm-provider': 'gemini',
      'x-llm-key': 'secret-key-value',
      'x-llm-tier': 'fast',
    });
  });

  it('includes model and base URL overrides when present', () => {
    const headers = buildByokHeaders(
      { ...key, model: 'gemini-x', baseUrl: 'http://localhost:1234/v1' },
      'reasoning',
    );
    expect(headers['x-llm-model']).toBe('gemini-x');
    expect(headers['x-llm-base-url']).toBe('http://localhost:1234/v1');
  });

  it('returns empty headers without a key', () => {
    expect(buildByokHeaders(undefined, 'fast')).toEqual({});
  });
});
