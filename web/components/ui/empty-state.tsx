'use client';

import { type LucideIcon } from 'lucide-react';
import { Button } from './button';
import { cn } from '@/lib/utils/cn';

export function EmptyState({
  icon: Icon,
  headline,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  headline: string;
  description: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-[var(--qg-radius-card)] border border-dashed border-border-strong bg-card px-6 py-12 text-center',
        className,
      )}
    >
      <Icon className="h-6 w-6 text-muted" aria-hidden />
      <h2 className="font-display text-[15px] font-semibold">{headline}</h2>
      <p className="max-w-sm text-[13px] text-text-2">{description}</p>
      {action ? (
        <Button variant="ghost" className="mt-2" onClick={action.onClick}>
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}
