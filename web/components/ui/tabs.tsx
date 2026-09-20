'use client';

import { cn } from '@/lib/utils/cn';

export type TabItem = { value: string; label: string };

/** Underline-style tabs; active = accent text + 2px accent underline. */
export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cn('flex gap-1 border-b border-border', className)}>
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors duration-[var(--dur)]',
              active
                ? 'border-accent text-accent'
                : 'border-transparent text-text-2 hover:text-text',
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
