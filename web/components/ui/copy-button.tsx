'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/cn';

export function CopyButton({
  text,
  label = 'Copy code',
  className,
}: {
  text: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // clipboard API unavailable (e.g. insecure context) — still show feedback
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={label}
      className={cn(
        'rounded-[var(--radius)] p-1.5 text-muted transition-colors duration-[var(--dur)] hover:bg-card hover:text-text',
        className,
      )}
    >
      {copied ? (
        <Check className="h-4 w-4" aria-hidden />
      ) : (
        <Copy className="h-4 w-4" aria-hidden />
      )}
    </button>
  );
}

/** Copy that shows a toast (used for export-style copies outside code blocks). */
export async function copyWithToast(text: string, toastMessage = 'Copied to clipboard') {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(toastMessage);
  } catch {
    toast.error('Clipboard is unavailable in this browser.');
  }
}
