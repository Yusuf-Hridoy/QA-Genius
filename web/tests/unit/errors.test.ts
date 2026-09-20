import { describe, expect, it } from 'vitest';
import { APICallError } from 'ai';
import {
  AppError,
  BadModelOutputError,
  ByokRequiredError,
  ContentBlockedError,
  InternalError,
  InvalidKeyError,
  ProviderRateLimitedError,
  ProviderUnavailableError,
  isJsonModeUnsupported,
  mapProviderError,
} from '@/lib/llm/errors';

function apiError(statusCode: number, message: string, responseHeaders?: Record<string, string>) {
  return new APICallError({
    message,
    url: 'https://api.example.com/v1/chat',
    requestBodyValues: {},
    statusCode,
    responseHeaders,
    isRetryable: false,
  });
}

describe('mapProviderError', () => {
  it('passes AppError through unchanged', () => {
    const error = new ByokRequiredError();
    expect(mapProviderError(error)).toBe(error);
  });

  it('maps 401/403 to invalid_key', () => {
    expect(mapProviderError(apiError(401, 'unauthorized'))).toBeInstanceOf(InvalidKeyError);
    expect(mapProviderError(apiError(403, 'forbidden'))).toBeInstanceOf(InvalidKeyError);
  });

  it('maps 429 with retry-after', () => {
    const mapped = mapProviderError(apiError(429, 'slow down', { 'retry-after': '30' }));
    expect(mapped).toBeInstanceOf(ProviderRateLimitedError);
    expect(mapped.details?.retryAfter).toBe(30);
  });

  it('maps 5xx to provider_unavailable', () => {
    expect(mapProviderError(apiError(503, 'down'))).toBeInstanceOf(ProviderUnavailableError);
  });

  it('maps content-filter errors to content_blocked', () => {
    expect(mapProviderError(apiError(400, 'content_policy_violation'))).toBeInstanceOf(
      ContentBlockedError,
    );
  });

  it('maps network-style errors to provider_unavailable', () => {
    expect(mapProviderError(new Error('fetch failed'))).toBeInstanceOf(ProviderUnavailableError);
    expect(mapProviderError(new Error('socket timeout'))).toBeInstanceOf(ProviderUnavailableError);
  });

  it('maps unknown errors to internal', () => {
    expect(mapProviderError(new Error('weird'))).toBeInstanceOf(InternalError);
  });

  it('caps bad_model_output excerpts at 500 chars', () => {
    const error = new BadModelOutputError('x'.repeat(800));
    expect((error.details?.rawExcerpt as string).length).toBe(500);
  });
});

describe('AppError contract', () => {
  it('serialises to the public error shape', () => {
    const json = new AppError('validation_error', 422, 'Fix it.', {
      issues: [{ path: 'a', message: 'required' }],
    }).toJson();
    expect(json).toEqual({
      error: 'validation_error',
      message: 'Fix it.',
      details: { issues: [{ path: 'a', message: 'required' }] },
    });
  });
});

describe('isJsonModeUnsupported', () => {
  it('detects structured-output rejections', () => {
    expect(isJsonModeUnsupported(new Error('response_format is not supported'))).toBe(true);
    expect(isJsonModeUnsupported(new Error('json_schema not allowed'))).toBe(true);
    expect(isJsonModeUnsupported(new Error('out of credits'))).toBe(false);
  });
});
