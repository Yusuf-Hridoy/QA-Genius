'use client';

import Link from 'next/link';
import { AlertTriangle, KeyRound } from 'lucide-react';
import { useKeysStore, type StoredKey } from '@/lib/store/keys';
import { PROVIDERS } from '@/lib/llm/providers';
import { Pill } from '@/components/ui/pill';

export function useDefaultKey(): StoredKey | undefined {
  return useKeysStore((s) => s.keys.find((k) => k.id === (s.defaultKeyId ?? s.keys[0]?.id)));
}

export function KeyBadge() {
  const defaultKey = useDefaultKey();

  if (!defaultKey) {
    return (
      <Link href="/settings/keys" className="block">
        <Pill tone="warn">
          <AlertTriangle className="h-3 w-3" aria-hidden />
          No key — add one
        </Pill>
      </Link>
    );
  }

  return (
    <Link href="/settings/keys" className="block">
      <Pill tone="ok">
        <KeyRound className="h-3 w-3" aria-hidden />
        {PROVIDERS[defaultKey.provider].displayName} · your key · never stored
      </Pill>
    </Link>
  );
}
