import { beforeEach, describe, expect, it } from 'vitest';
import { useKeysStore } from '@/lib/store/keys';
import { useProjectStore } from '@/lib/store/project';

function reset() {
  useKeysStore.setState({ keys: [], defaultKeyId: null, tier: 'fast' });
}

const baseKey = {
  provider: 'gemini' as const,
  label: 'Gemini',
  apiKey: 'test-key-value',
};

beforeEach(() => {
  reset();
  localStorage.clear();
});

describe('keys store', () => {
  it('first added key becomes the default', () => {
    const id = useKeysStore.getState().addKey(baseKey);
    const state = useKeysStore.getState();
    expect(state.keys).toHaveLength(1);
    expect(state.defaultKeyId).toBe(id);
    expect(state.keys[0]?.createdAt).toBeTruthy();
  });

  it('removing the default reassigns it to another key', () => {
    const first = useKeysStore.getState().addKey(baseKey);
    const second = useKeysStore.getState().addKey({ ...baseKey, provider: 'groq' });
    useKeysStore.getState().setDefault(first);
    useKeysStore.getState().removeKey(first);
    const state = useKeysStore.getState();
    expect(state.keys).toHaveLength(1);
    expect(state.defaultKeyId).toBe(second);
  });

  it('removing the last key clears the default', () => {
    const id = useKeysStore.getState().addKey(baseKey);
    useKeysStore.getState().removeKey(id);
    expect(useKeysStore.getState().defaultKeyId).toBeNull();
  });

  it('setDefault and setTier update state', () => {
    const id = useKeysStore.getState().addKey(baseKey);
    const other = useKeysStore.getState().addKey({ ...baseKey, provider: 'openai' });
    useKeysStore.getState().setDefault(other);
    useKeysStore.getState().setTier('reasoning');
    const state = useKeysStore.getState();
    expect(state.defaultKeyId).toBe(other);
    expect(state.tier).toBe('reasoning');
    expect(state.getDefault()?.id).toBe(other);
    expect(id).not.toBe(other);
  });

  it('persists to localStorage and rehydrates', async () => {
    useKeysStore.getState().addKey(baseKey);
    const raw = localStorage.getItem('qag.keys.v1');
    expect(raw).toBeTruthy();
    const persisted = JSON.parse(raw as string) as { state: { keys: unknown[] } };
    expect(persisted.state.keys).toHaveLength(1);
  });
});

describe('project store', () => {
  it('seeds the Aurora Storefront demo project by default', () => {
    expect(useProjectStore.getState().project.name).toBe('Aurora Storefront');
  });

  it('updates name and stack', () => {
    useProjectStore.getState().setProject({ name: 'Aurora Storefront', stack: 'Next.js · Vitest' });
    expect(useProjectStore.getState().project.stack).toBe('Next.js · Vitest');
  });
});
