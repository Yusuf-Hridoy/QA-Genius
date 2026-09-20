'use client';

import { Menu } from 'lucide-react';
import { resolveModel, type Tier } from '@/lib/llm/providers';
import { useKeysStore } from '@/lib/store/keys';
import { cn } from '@/lib/utils/cn';
import { useShell } from './shell-context';
import { useDefaultKey } from './key-badge';

function TierSegmented() {
  const tier = useKeysStore((s) => s.tier);
  const setTier = useKeysStore((s) => s.setTier);
  const defaultKey = useDefaultKey();
  const modelName = defaultKey ? resolveModel(defaultKey.provider, tier, defaultKey.model) : null;

  return (
    <div className="flex flex-col items-end gap-0.5">
      <div
        role="radiogroup"
        aria-label="Model tier"
        className="flex overflow-hidden rounded-[var(--qg-radius)] border border-border-strong bg-card"
      >
        {(['fast', 'reasoning'] as Tier[]).map((t) => (
          <button
            key={t}
            role="radio"
            aria-checked={tier === t}
            onClick={() => setTier(t)}
            className={cn(
              'px-3 py-1.5 text-[12px] font-medium capitalize transition-colors duration-[var(--qg-dur)]',
              tier === t ? 'bg-accent text-accent-ink' : 'text-text-2 hover:bg-card-2',
            )}
          >
            {t}
          </button>
        ))}
      </div>
      <span className="font-mono text-[11px] text-muted">{modelName ?? 'No key selected'}</span>
    </div>
  );
}

export function TopBar({ children }: { children?: React.ReactNode }) {
  const { pageInfo, setDrawerOpen } = useShell();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border px-4">
      <div className="flex items-center gap-2">
        <button
          className="rounded-[var(--qg-radius)] p-2 text-text-2 hover:bg-card-2 lg:hidden"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>
        <nav aria-label="Breadcrumb" className="text-[13px] text-text-2">
          <ol className="flex items-center gap-1.5">
            <li>{pageInfo.workspace}</li>
            {pageInfo.tab ? (
              <>
                <li aria-hidden className="text-muted">
                  ›
                </li>
                <li aria-current="page" className="font-medium text-text">
                  {pageInfo.tab}
                </li>
              </>
            ) : null}
          </ol>
        </nav>
      </div>
      <div className="flex items-center gap-3">
        {children}
        <TierSegmented />
      </div>
    </header>
  );
}
