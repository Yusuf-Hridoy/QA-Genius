'use client';

import { useId } from 'react';
import { cn } from '@/lib/utils/cn';

export function Checkbox({
  label,
  checked,
  onCheckedChange,
  disabled = false,
  className,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <label
      className={cn(
        'inline-flex cursor-pointer items-center gap-2 text-[13px] text-text-2',
        disabled && 'cursor-not-allowed opacity-60',
        className,
      )}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onCheckedChange(e.target.checked)}
        className="h-4 w-4 rounded-[3px] border-border-strong accent-[var(--qg-accent)]"
      />
      {label}
    </label>
  );
}
