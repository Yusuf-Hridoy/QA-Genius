'use client';

import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react';
import { cn } from '@/lib/utils/cn';

/**
 * Label + control + helper/error + optional char counter.
 * Counter turns warn-fg above 90% of max and bad-fg above max.
 */
export function FormField({
  label,
  htmlFor,
  helper,
  error,
  maxChars,
  charCount,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  helper?: string;
  error?: string;
  maxChars?: number;
  charCount?: number;
  children: ReactNode;
  className?: string;
}) {
  const autoId = useId();
  const id = htmlFor ?? autoId;
  const helperId = `${id}-helper`;
  const errorId = `${id}-error`;

  // Associate the label with the control by injecting the generated id.
  // When htmlFor is set explicitly, the caller wires the id itself (e.g. a
  // control wrapped in a positioning div) — injecting here would duplicate it.
  const describedBy = error ? errorId : helper ? helperId : undefined;
  const control =
    isValidElement(children) && !htmlFor
      ? cloneElement(children as ReactElement<Record<string, unknown>>, {
          id,
          ...(describedBy ? { 'aria-describedby': describedBy } : {}),
        })
      : children;

  let counterTone = 'text-muted';
  if (maxChars !== undefined && charCount !== undefined) {
    if (charCount > maxChars) counterTone = 'text-bad-fg';
    else if (charCount > maxChars * 0.9) counterTone = 'text-warn-fg';
  }

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-[13px] font-medium">
          {label}
        </label>
        {maxChars !== undefined && charCount !== undefined ? (
          <span className={cn('text-[12px]', counterTone)}>
            {charCount} / {maxChars}
          </span>
        ) : null}
      </div>
      {control}
      {error ? (
        <p id={errorId} className="text-[12px] text-bad-fg" role="alert">
          {error}
        </p>
      ) : helper ? (
        <p id={helperId} className="text-[12px] text-muted">
          {helper}
        </p>
      ) : null}
    </div>
  );
}
