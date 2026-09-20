'use client';

import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils/cn';

const CONTROL_CLASSES =
  'w-full rounded-[var(--radius)] border border-border-strong bg-card px-3 text-[14px] text-text placeholder:text-muted focus-visible:outline-none';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(CONTROL_CLASSES, 'h-9', className)} {...props} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(CONTROL_CLASSES, 'min-h-24 resize-y py-2 leading-normal', className)}
      {...props}
    />
  );
});
