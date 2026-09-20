import { NextResponse } from 'next/server';
import { AppError, mapProviderError } from '@/lib/llm/errors';
import { log } from '@/lib/utils/log';

const NO_STORE = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' } as const;

/**
 * Wrap an API handler: AppError → its JSON contract; unknown errors are mapped
 * via mapProviderError (unknown shape → 500 internal). Logs requestId/kind/error
 * name only — never bodies or headers.
 */
export function withApiErrors<Args extends unknown[]>(
  handler: (...args: Args) => Promise<Response>,
  context: () => string,
): (...args: Args) => Promise<Response> {
  return async (...args: Args) => {
    try {
      return await handler(...args);
    } catch (error) {
      const appError = error instanceof AppError ? error : mapProviderError(error);
      if (!(error instanceof AppError)) {
        log.error(`api error ${context()}: ${appError.code}`, error);
      }
      return NextResponse.json(appError.toJson(), { status: appError.status, headers: NO_STORE });
    }
  };
}

export { NO_STORE };
