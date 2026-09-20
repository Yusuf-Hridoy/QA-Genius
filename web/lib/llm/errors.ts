import { APICallError } from 'ai';

export type ErrorCode =
  | 'unknown_kind'
  | 'byok_required'
  | 'invalid_key'
  | 'unsupported_provider'
  | 'content_blocked'
  | 'validation_error'
  | 'input_too_large'
  | 'provider_rate_limited'
  | 'bad_model_output'
  | 'provider_unavailable'
  | 'internal';

export type ErrorDetails = Record<string, unknown>;

export class AppError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details?: ErrorDetails;

  constructor(code: ErrorCode, status: number, message: string, details?: ErrorDetails) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.status = status;
    this.details = details;
  }

  toJson() {
    return {
      error: this.code,
      message: this.message,
      ...(this.details ? { details: this.details } : {}),
    };
  }
}

export class UnknownKindError extends AppError {
  constructor(kind: string) {
    super('unknown_kind', 404, `Unknown generator kind: ${kind}.`);
  }
}

export class ByokRequiredError extends AppError {
  constructor(message = 'Add an API key in Settings to generate.') {
    super('byok_required', 401, message);
  }
}

export class InvalidKeyError extends AppError {
  constructor() {
    super('invalid_key', 401, 'Your provider rejected this key. Check it in Settings.');
  }
}

export class UnsupportedProviderError extends AppError {
  constructor(message = "That provider isn't supported.") {
    super('unsupported_provider', 400, message);
  }
}

export class ContentBlockedError extends AppError {
  constructor() {
    super('content_blocked', 400, 'Your provider blocked this input. Rephrase and try again.');
  }
}

export class RequestValidationError extends AppError {
  constructor(issues: { path: string; message: string }[]) {
    super('validation_error', 422, 'Fix the highlighted fields.', { issues });
  }
}

export class InputTooLargeError extends AppError {
  constructor() {
    super('input_too_large', 422, 'Input is too large (max 50,000 characters).');
  }
}

export class ProviderRateLimitedError extends AppError {
  constructor(retryAfter?: number) {
    super(
      'provider_rate_limited',
      429,
      'Your provider rate-limited this key. Try again in a moment.',
      {
        ...(retryAfter !== undefined ? { retryAfter } : {}),
      },
    );
  }
}

export class BadModelOutputError extends AppError {
  constructor(rawExcerpt: string) {
    super(
      'bad_model_output',
      502,
      "The model returned output that couldn't be read. Try again or switch tier.",
      { rawExcerpt: rawExcerpt.slice(0, 500) },
    );
  }
}

export class ProviderUnavailableError extends AppError {
  constructor() {
    super(
      'provider_unavailable',
      503,
      'Your provider is unavailable right now. Try again shortly.',
    );
  }
}

export class InternalError extends AppError {
  constructor() {
    super('internal', 500, 'Something went wrong. Try again.');
  }
}

const CONTENT_FILTER_PATTERNS = [
  /content_policy/i,
  /content filter/i,
  /safety/i,
  /harmful/i,
  /blocked/i,
  /moderation/i,
];

const JSON_MODE_PATTERNS = [
  /response_format/i,
  /json_schema/i,
  /json schema/i,
  /structured output/i,
  /response format/i,
];

/** True when the provider rejected the structured-output / JSON-schema mode. */
export function isJsonModeUnsupported(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return JSON_MODE_PATTERNS.some((pattern) => pattern.test(text));
}

/** Map any provider/AI SDK error to the public error contract (Appendix B messages). */
export function mapProviderError(error: unknown): AppError {
  if (error instanceof AppError) return error;

  const message = error instanceof Error ? error.message : String(error);
  const text = error instanceof Error ? `${error.name} ${message}` : message;

  if (error instanceof APICallError) {
    const status = error.statusCode;
    if (status === 401 || status === 403) return new InvalidKeyError();
    if (status === 429) {
      const retryAfterHeader = error.responseHeaders?.['retry-after'];
      const retryAfter = Array.isArray(retryAfterHeader)
        ? Number(retryAfterHeader[0])
        : Number(retryAfterHeader);
      return new ProviderRateLimitedError(Number.isFinite(retryAfter) ? retryAfter : undefined);
    }
    if (status !== undefined && status >= 500) return new ProviderUnavailableError();
    if (CONTENT_FILTER_PATTERNS.some((pattern) => pattern.test(text)))
      return new ContentBlockedError();
    if (status === 400) {
      if (CONTENT_FILTER_PATTERNS.some((pattern) => pattern.test(text)))
        return new ContentBlockedError();
      return new ProviderUnavailableError();
    }
  }

  if (CONTENT_FILTER_PATTERNS.some((pattern) => pattern.test(text)))
    return new ContentBlockedError();

  if (
    /timeout|timed out|econn|enotfound|eai_again|network|socket|fetch failed|unavailable/i.test(
      text,
    )
  ) {
    return new ProviderUnavailableError();
  }

  return new InternalError();
}
