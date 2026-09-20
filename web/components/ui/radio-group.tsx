'use client';

import { useId } from 'react';
import { cn } from '@/lib/utils/cn';

export type RadioOption<T extends string> = { value: T; label: string };

export function RadioGroup<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label?: string;
  options: RadioOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const groupId = useId();
  return (
    <fieldset className={cn('flex flex-col gap-1.5', className)}>
      {label ? <legend className="text-[13px] font-medium">{label}</legend> : null}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {options.map((option) => (
          <label
            key={option.value}
            className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-text-2"
          >
            <input
              type="radio"
              name={groupId}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="h-4 w-4 border-border-strong accent-[var(--qg-accent)]"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
