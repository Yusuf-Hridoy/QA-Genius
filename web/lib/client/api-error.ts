'use client';

import { toast } from 'sonner';
import type { ApiError } from './use-object-stream';

/**
 * Render an API error as a toast. byok_required gets an "Open settings"
 * action; provider_rate_limited appends the retry delay when known.
 */
export function showApiErrorToast(error: ApiError) {
  let message = error.message;
  if (error.code === 'provider_rate_limited') {
    const retryAfter = error.details?.retryAfter;
    if (typeof retryAfter === 'number') {
      message = `${message} Try again in ${retryAfter}s.`;
    }
  }
  toast.error(message, {
    ...(error.code === 'byok_required'
      ? {
          action: {
            label: 'Open settings',
            onClick: () => (window.location.href = '/settings/keys'),
          },
        }
      : {}),
  });
}

export function showNoKeyToast() {
  toast.error('Add an API key to generate.', {
    action: { label: 'Open settings', onClick: () => (window.location.href = '/settings/keys') },
  });
}

export function showSuspiciousToast() {
  toast.info('This input looks like a prompt-injection attempt; the output may be unhelpful.');
}
