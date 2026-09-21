/**
 * Mid-stream error sentinel shared by the server streamer and the client hook.
 * No server-only imports here: both `lib/llm/generate.ts` and
 * `lib/client/use-object-stream.ts` import from this module.
 */

export const STREAM_ERROR_SENTINEL = '\n\u0000';
export const STREAM_ERROR_KEY = '__qagError';

export function encodeStreamError(code: string, message: string): string {
  return `${STREAM_ERROR_SENTINEL}${JSON.stringify({ [STREAM_ERROR_KEY]: { code, message } })}`;
}

/** Split accumulated stream text into JSON text + an optional mid-stream error. */
export function decodeStreamError(accumulated: string): {
  jsonText: string;
  code?: string;
  message?: string;
} {
  const idx = accumulated.indexOf(STREAM_ERROR_SENTINEL);
  if (idx === -1) return { jsonText: accumulated };
  const jsonText = accumulated.slice(0, idx);
  try {
    const parsed = JSON.parse(accumulated.slice(idx + STREAM_ERROR_SENTINEL.length)) as {
      [STREAM_ERROR_KEY]?: { code?: string; message?: string };
    };
    const err = parsed[STREAM_ERROR_KEY];
    if (err && typeof err.code === 'string') {
      return { jsonText, code: err.code, message: err.message };
    }
  } catch {
    // malformed sentinel — treat as a generic mid-stream failure
    return { jsonText, code: 'provider_unavailable' };
  }
  return { jsonText };
}
