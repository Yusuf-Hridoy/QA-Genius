'use client';

import Link from 'next/link';
import { cn } from '@/lib/utils/cn';
import { STEPS, canVisit, stepStatus, type StepId } from '@/lib/pipeline/steps';
import { useRunStore } from '@/lib/store/run';

/** Pipeline stepper for the Requirements workspace. */
export function RunStepper({
  current,
  interactive = true,
}: {
  current: StepId;
  interactive?: boolean;
}) {
  const run = useRunStore((s) => s.run);

  return (
    <ol aria-label="Requirements pipeline" className="flex flex-wrap items-center gap-1.5">
      {STEPS.map((step, i) => {
        const status = stepStatus(run, current, step.id);
        const allowed = canVisit(run, step.id);
        const isCurrent = step.id === current;
        const pill = (
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors duration-[var(--dur)]',
              status === 'done' && 'border-border bg-card-2 text-text',
              isCurrent && 'border-accent bg-accent-soft text-accent',
              status === 'todo' && !isCurrent && 'border-border bg-transparent text-muted',
              !allowed && !isCurrent && 'opacity-60',
            )}
            aria-current={isCurrent ? 'step' : undefined}
          >
            <span
              aria-hidden
              className={cn(
                'inline-flex h-5 w-5 items-center justify-center rounded-full font-mono text-[11px]',
                isCurrent ? 'bg-accent text-accent-ink' : 'bg-card-2 text-text-2',
              )}
            >
              {i + 1}
            </span>
            {step.label}
          </span>
        );
        if (isCurrent || !allowed || !interactive) {
          return <li key={step.id}>{pill}</li>;
        }
        return (
          <li key={step.id}>
            <Link href={step.href} aria-label={`Go to ${step.label}`}>
              {pill}
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
