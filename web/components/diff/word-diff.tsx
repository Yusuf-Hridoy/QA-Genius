'use client';

import type { Change } from 'diff';
import { cn } from '@/lib/utils/cn';

/** Inline word diff: added = ok-bg underline, removed = bad-bg strikethrough. */
export function WordDiff({ parts }: { parts: Change[] }) {
  return (
    <span>
      {parts.map((part, i) => (
        <span
          key={i}
          className={cn(
            part.added && 'rounded-[3px] bg-ok-bg underline decoration-ok-fg underline-offset-2',
            part.removed && 'rounded-[3px] bg-bad-bg line-through decoration-bad-fg',
          )}
        >
          {part.value}
        </span>
      ))}
    </span>
  );
}
