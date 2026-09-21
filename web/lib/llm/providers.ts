import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { createGroq } from '@ai-sdk/groq';
import { createOpenAI } from '@ai-sdk/openai';
import { createAnthropic } from '@ai-sdk/anthropic';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import type { LanguageModel } from 'ai';
import { UnsupportedProviderError } from './errors';

export const PROVIDER_IDS = [
  'gemini',
  'groq',
  'openai',
  'anthropic',
  'openrouter',
  'openai-compatible',
] as const;

export type ProviderId = (typeof PROVIDER_IDS)[number];
export type Tier = 'fast' | 'reasoning';

export type ProviderMeta = {
  id: ProviderId;
  displayName: string;
  keyHelpUrl: string; // '' when none
  needsBaseUrl: boolean;
  defaultModels: Record<Tier, string>;
  supportsJsonMode: boolean; // hint for generate.ts fallback
  /** Whether the default models can read attached screenshots. */
  supportsVision: boolean;
};

export const PROVIDERS: Record<ProviderId, ProviderMeta> = {
  gemini: {
    id: 'gemini',
    displayName: 'Google Gemini',
    keyHelpUrl: 'https://aistudio.google.com/app/apikey',
    needsBaseUrl: false,
    defaultModels: { fast: 'gemini-2.5-flash-lite', reasoning: 'gemini-2.5-flash' },
    supportsJsonMode: true,
    supportsVision: true,
  },
  groq: {
    id: 'groq',
    displayName: 'Groq',
    keyHelpUrl: 'https://console.groq.com/keys',
    needsBaseUrl: false,
    defaultModels: { fast: 'llama-3.1-8b-instant', reasoning: 'llama-3.3-70b-versatile' },
    supportsJsonMode: true,
    supportsVision: false,
  },
  openai: {
    id: 'openai',
    displayName: 'OpenAI',
    keyHelpUrl: 'https://platform.openai.com/api-keys',
    needsBaseUrl: false,
    defaultModels: { fast: 'gpt-4o-mini', reasoning: 'gpt-4o-mini' },
    supportsJsonMode: true,
    supportsVision: true,
  },
  anthropic: {
    id: 'anthropic',
    displayName: 'Anthropic',
    keyHelpUrl: 'https://console.anthropic.com/settings/keys',
    needsBaseUrl: false,
    defaultModels: { fast: 'claude-3-5-haiku-latest', reasoning: 'claude-sonnet-4-5' },
    supportsJsonMode: true,
    supportsVision: true,
  },
  openrouter: {
    id: 'openrouter',
    displayName: 'OpenRouter',
    keyHelpUrl: 'https://openrouter.ai/keys',
    needsBaseUrl: false,
    defaultModels: {
      fast: 'google/gemini-2.5-flash-lite',
      reasoning: 'google/gemini-2.5-flash',
    },
    supportsJsonMode: true,
    supportsVision: true,
  },
  'openai-compatible': {
    id: 'openai-compatible',
    displayName: 'OpenAI-compatible URL (Ollama, LM Studio, vLLM)',
    keyHelpUrl: '',
    needsBaseUrl: true,
    defaultModels: { fast: 'llama3.1', reasoning: 'llama3.1' },
    supportsJsonMode: false,
    supportsVision: false,
  },
};

/** Order used in selects (brief Appendix A.4). */
export const PROVIDER_SELECT_ORDER: ProviderId[] = [
  'gemini',
  'groq',
  'openrouter',
  'openai',
  'anthropic',
  'openai-compatible',
];

export function resolveModel(p: ProviderId, tier: Tier, override?: string): string {
  return override?.trim() || PROVIDERS[p].defaultModels[tier];
}

export function createModel(
  p: ProviderId,
  apiKey: string,
  modelId: string,
  baseUrl?: string,
): LanguageModel {
  switch (p) {
    case 'gemini':
      return createGoogleGenerativeAI({ apiKey })(modelId);
    case 'groq':
      return createGroq({ apiKey })(modelId);
    case 'openai':
      return createOpenAI({ apiKey })(modelId);
    case 'anthropic':
      return createAnthropic({ apiKey })(modelId);
    case 'openrouter':
      return createOpenAICompatible({
        name: 'openrouter',
        apiKey,
        baseURL: 'https://openrouter.ai/api/v1',
      })(modelId);
    case 'openai-compatible':
      if (!baseUrl) {
        throw new UnsupportedProviderError(
          'Base URL is required for an OpenAI-compatible provider.',
        );
      }
      return createOpenAICompatible({
        name: 'custom',
        apiKey: apiKey || 'not-needed',
        baseURL: baseUrl,
      })(modelId);
  }
}
