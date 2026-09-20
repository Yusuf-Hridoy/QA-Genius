import { z } from 'zod';
import { PROVIDER_IDS, type ProviderId, type Tier } from './providers';
import { ByokRequiredError, UnsupportedProviderError } from './errors';
import type { StoredKey } from '@/lib/store/keys';

export type Byok = {
  provider: ProviderId;
  apiKey: string;
  model?: string;
  baseUrl?: string;
  tier: Tier;
};

const PRINTABLE_ASCII = /^[\x20-\x7E]+$/;

const byokSchema = z.object({
  provider: z.enum(PROVIDER_IDS),
  apiKey: z.string().min(1).max(512).regex(PRINTABLE_ASCII),
  model: z.string().max(300).optional(),
  baseUrl: z
    .string()
    .regex(/^https?:\/\//, 'Base URL must start with http(s)://')
    .optional(),
  tier: z.enum(['fast', 'reasoning']).catch('fast'),
});

/**
 * Parse and validate BYOK headers (brief §6.3).
 * Missing key/provider → byok_required; unknown provider → unsupported_provider;
 * malformed key → byok_required; missing/invalid base URL for openai-compatible → unsupported_provider.
 */
export function parseByok(headers: Headers): Byok {
  const providerHeader = headers.get('x-llm-provider');
  const apiKeyHeader = headers.get('x-llm-key');

  if (!providerHeader || !apiKeyHeader) {
    throw new ByokRequiredError();
  }
  if (!(PROVIDER_IDS as readonly string[]).includes(providerHeader)) {
    throw new UnsupportedProviderError();
  }

  const parsed = byokSchema.safeParse({
    provider: providerHeader,
    apiKey: apiKeyHeader,
    model: headers.get('x-llm-model') ?? undefined,
    baseUrl: headers.get('x-llm-base-url') ?? undefined,
    tier: headers.get('x-llm-tier') ?? undefined,
  });

  if (!parsed.success) {
    const issues = parsed.error.issues;
    const baseUrlIssue = issues.find((i) => i.path.includes('baseUrl'));
    if (providerHeader === 'openai-compatible') {
      throw new UnsupportedProviderError(
        baseUrlIssue
          ? 'Base URL must start with http(s)://'
          : 'Base URL is required for an OpenAI-compatible provider.',
      );
    }
    throw new ByokRequiredError('Add a valid API key in Settings to generate.');
  }

  const value = parsed.data;
  if (value.provider === 'openai-compatible' && !value.baseUrl) {
    throw new UnsupportedProviderError('Base URL is required for an OpenAI-compatible provider.');
  }

  return {
    provider: value.provider,
    apiKey: value.apiKey,
    ...(value.model ? { model: value.model } : {}),
    ...(value.baseUrl ? { baseUrl: value.baseUrl } : {}),
    tier: value.tier,
  };
}

/** Client-side: build the request headers for one stored key. Never put these in URLs or bodies. */
export function buildByokHeaders(key: StoredKey | undefined, tier: Tier): Record<string, string> {
  if (!key) return {};
  const headers: Record<string, string> = {
    'x-llm-provider': key.provider,
    'x-llm-key': key.apiKey,
    'x-llm-tier': tier,
  };
  if (key.model) headers['x-llm-model'] = key.model;
  if (key.baseUrl) headers['x-llm-base-url'] = key.baseUrl;
  return headers;
}
