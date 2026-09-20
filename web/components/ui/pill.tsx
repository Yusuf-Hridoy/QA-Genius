import type { ReactNode } from 'react';
import { cn } from '@/lib/utils/cn';

export type PillTone = 'ok' | 'warn' | 'bad' | 'info' | 'neutral' | 'accent';

const TONE_CLASSES: Record<PillTone, string> = {
  ok: 'bg-ok-bg text-ok-fg',
  warn: 'bg-warn-bg text-warn-fg',
  bad: 'bg-bad-bg text-bad-fg',
  info: 'bg-info-bg text-info-fg',
  neutral: 'bg-card-2 text-text-2',
  accent: 'bg-accent-soft text-accent',
};

export function Pill({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: PillTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-[3px] text-[11px] font-medium leading-none',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
