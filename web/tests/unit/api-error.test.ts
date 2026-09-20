import { describe, expect, it, vi } from 'vitest';

const { toastErrorMock, toastInfoMock, toastSuccessMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    error: toastErrorMock,
    info: toastInfoMock,
    success: toastSuccessMock,
  },
}));

import { showApiErrorToast, showNoKeyToast, showSuspiciousToast } from '@/lib/client/api-error';
import type { ApiError } from '@/lib/client/use-object-stream';

function apiError(message: string, code?: string, details?: Record<string, unknown>): ApiError {
  const error = new Error(message) as ApiError;
  error.code = code;
  error.details = details;
  return error;
}

describe('showApiErrorToast', () => {
  it('shows the server message', () => {
    showApiErrorToast(apiError('Your provider rejected this key.'));
    expect(toastErrorMock).toHaveBeenCalledWith(
      'Your provider rejected this key.',
      expect.anything(),
    );
  });

  it('adds an Open settings action for byok_required', () => {
    showApiErrorToast(apiError('Add an API key in Settings to generate.', 'byok_required'));
    const options = toastErrorMock.mock.calls[0]?.[1] as {
      action: { label: string };
    };
    expect(options.action.label).toBe('Open settings');
  });

  it('appends retry seconds for provider_rate_limited', () => {
    showApiErrorToast(
      apiError('Your provider rate-limited this key.', 'provider_rate_limited', {
        retryAfter: 42,
      }),
    );
    expect(toastErrorMock.mock.calls[0]?.[0]).toContain('Try again in 42s.');
  });

  it('shows a warning toast for suspicious input', () => {
    showSuspiciousToast();
    expect(toastInfoMock).toHaveBeenCalledOnce();
  });

  it('shows the no-key toast with an action', () => {
    showNoKeyToast();
    const options = toastErrorMock.mock.calls[0]?.[1] as { action: { label: string } };
    expect(options.action.label).toBe('Open settings');
  });
});
