'use client';

import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const buttonVariants = cva(
  'relative inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--radius)] text-[13px] font-medium transition-colors duration-[var(--dur)] focus-visible:outline-none disabled:pointer-events-none',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-ink hover:bg-accent-hover',
        secondary: 'bg-card border border-border-strong text-text hover:bg-card-2',
        ghost: 'bg-transparent text-text-2 hover:bg-card-2',
        danger: 'bg-bad-bg text-bad-fg hover:opacity-90',
      },
      size: {
        default: 'h-9 px-3.5',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'default' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, loading = false, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled}
      {...props}
    >
      <span className={cn('inline-flex items-center gap-1.5', loading && 'invisible')}>
        {children}
      </span>
      {loading ? (
        <Loader2
          className="absolute h-4 w-4 animate-spin"
          aria-hidden
          // keep layout centred over the hidden content
          style={{ position: 'absolute' }}
        />
      ) : null}
      {loading ? <span className="sr-only">Loading</span> : null}
    </button>
  );
});
