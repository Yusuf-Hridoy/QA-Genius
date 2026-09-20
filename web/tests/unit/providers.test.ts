import { describe, expect, it } from 'vitest';
import {
  PROVIDERS,
  PROVIDER_IDS,
  PROVIDER_SELECT_ORDER,
  createModel,
  resolveModel,
} from '@/lib/llm/providers';
import { UnsupportedProviderError } from '@/lib/llm/errors';

describe('PROVIDERS registry', () => {
  it('has metadata for every provider id', () => {
    for (const id of PROVIDER_IDS) {
      const meta = PROVIDERS[id];
      expect(meta.id).toBe(id);
      expect(meta.displayName.length).toBeGreaterThan(0);
      expect(meta.defaultModels.fast.length).toBeGreaterThan(0);
      expect(meta.defaultModels.reasoning.length).toBeGreaterThan(0);
    }
  });

  it('only openai-compatible needs a base URL and lacks a key-help link', () => {
    for (const id of PROVIDER_IDS) {
      expect(PROVIDERS[id].needsBaseUrl).toBe(id === 'openai-compatible');
      if (id === 'openai-compatible') {
        expect(PROVIDERS[id].keyHelpUrl).toBe('');
      } else {
        expect(PROVIDERS[id].keyHelpUrl).toMatch(/^https:\/\//);
      }
    }
  });

  it('select order contains every provider', () => {
    expect([...PROVIDER_SELECT_ORDER].sort()).toEqual([...PROVIDER_IDS].sort());
  });
});

describe('resolveModel', () => {
  it('returns the tier default when no override', () => {
    expect(resolveModel('gemini', 'fast')).toBe(PROVIDERS.gemini.defaultModels.fast);
    expect(resolveModel('gemini', 'reasoning')).toBe(PROVIDERS.gemini.defaultModels.reasoning);
  });

  it('override wins, ignoring surrounding whitespace', () => {
    expect(resolveModel('gemini', 'fast', '  custom-model ')).toBe('custom-model');
  });

  it('blank override falls back to the default', () => {
    expect(resolveModel('groq', 'fast', '   ')).toBe(PROVIDERS.groq.defaultModels.fast);
  });
});

describe('createModel', () => {
  it('returns a model for every provider factory', () => {
    for (const id of PROVIDER_IDS) {
      if (id === 'openai-compatible') continue;
      const model = createModel(id, 'test-key', 'some-model');
      expect(model).toBeDefined();
    }
  });

  it('throws for openai-compatible without a base URL', () => {
    expect(() => createModel('openai-compatible', 'k', 'm')).toThrow(UnsupportedProviderError);
  });

  it('creates an openai-compatible model with a base URL', () => {
    const model = createModel('openai-compatible', '', 'llama3.1', 'http://localhost:11434/v1');
    expect(model).toBeDefined();
  });
});
