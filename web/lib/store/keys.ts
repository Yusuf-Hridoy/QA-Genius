'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ProviderId, Tier } from '@/lib/llm/providers';
import { newId } from '@/lib/utils/id';

export type StoredKey = {
  id: string; // nanoid
  provider: ProviderId;
  label: string; // user label, default = provider display name
  apiKey: string;
  baseUrl?: string; // only for 'openai-compatible'
  model?: string; // optional override for both tiers
  createdAt: string; // ISO
};

export type KeysState = {
  keys: StoredKey[];
  defaultKeyId: string | null;
  tier: Tier;
  addKey: (k: Omit<StoredKey, 'id' | 'createdAt'>) => string;
  removeKey: (id: string) => void;
  setDefault: (id: string) => void;
  setTier: (t: Tier) => void;
  getDefault: () => StoredKey | undefined;
};

/**
 * Browser-only store (persist → localStorage). Server components never import this.
 * Keys never leave the browser except as x-llm-* request headers.
 */
export const useKeysStore = create<KeysState>()(
  persist(
    (set, get) => ({
      keys: [],
      defaultKeyId: null,
      tier: 'fast',
      addKey: (k) => {
        const id = newId();
        set((state) => ({
          keys: [...state.keys, { ...k, id, createdAt: new Date().toISOString() }],
          // First key added becomes the default.
          defaultKeyId: state.defaultKeyId ?? id,
        }));
        return id;
      },
      removeKey: (id) => {
        set((state) => {
          const keys = state.keys.filter((k) => k.id !== id);
          let defaultKeyId = state.defaultKeyId;
          if (defaultKeyId === id) {
            defaultKeyId = keys[0]?.id ?? null;
          }
          return { keys, defaultKeyId };
        });
      },
      setDefault: (id) => {
        set({ defaultKeyId: id });
      },
      setTier: (t) => {
        set({ tier: t });
      },
      getDefault: () => {
        const { keys, defaultKeyId } = get();
        return keys.find((k) => k.id === defaultKeyId) ?? keys[0];
      },
    }),
    {
      name: 'qag.keys.v1',
      version: 1,
      migrate: (persisted) => persisted as KeysState, // stub for future shape changes
    },
  ),
);
