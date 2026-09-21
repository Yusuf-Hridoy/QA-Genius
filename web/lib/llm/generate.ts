import { generateText, streamObject } from 'ai';
import { ZodError, type z } from 'zod';
import { REGISTRY, type GeneratorKind, type GeneratorDef } from '@/lib/generators/kinds';
import { createModel, resolveModel, PROVIDERS } from './providers';
import { detectSuspicious } from './suspicious';
import { repairAndParse } from './repair';
import { isJsonModeUnsupported, mapProviderError } from './errors';
import {
  STREAM_ERROR_KEY,
  STREAM_ERROR_SENTINEL,
  decodeStreamError,
  encodeStreamError,
} from './stream-error';
import type { Byok } from './byok';
import { BadModelOutputError, InputTooLargeError, RequestValidationError } from './errors';

export type GenerateInput = {
  kind: GeneratorKind;
  body: unknown;
  byok: Byok;
  requestId: string;
};

const MAX_TOTAL_INPUT_CHARS = 50_000;

function collectSuspiciousAndSize(body: unknown): { suspicious: boolean; totalChars: number } {
  let suspicious = false;
  let totalChars = 0;
  const visit = (value: unknown) => {
    if (typeof value === 'string') {
      totalChars += value.length;
      if (!suspicious && detectSuspicious(value)) suspicious = true;
    } else if (Array.isArray(value)) {
      for (const item of value) visit(item);
    } else if (value !== null && typeof value === 'object') {
      for (const item of Object.values(value)) visit(item);
    }
  };
  visit(body);
  return { suspicious, totalChars };
}

function reAskSuffix(issues: string, rawExcerpt: string): string {
  return (
    `\n\nYour previous response was not valid JSON for the required schema. Errors:\n${issues}\n` +
    `Your previous response (first 4000 characters):\n${rawExcerpt.slice(0, 4000)}\n` +
    'Return ONLY the corrected JSON object.'
  );
}

function formatIssues(error: unknown): string {
  if (error instanceof ZodError) {
    return JSON.stringify(
      error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message })),
      null,
      2,
    );
  }
  if (error instanceof Error) return error.message;
  return String(error);
}

/** A stream part as yielded by the SDK result's fullStream. */
type FullStreamPart = { type: string; textDelta?: string; error?: unknown };
// Re-exported for tests and the client sentinel contract.
export { STREAM_ERROR_KEY, STREAM_ERROR_SENTINEL, decodeStreamError, encodeStreamError };

/**
 * Pull the first stream part before committing to a 200 response, so provider
 * errors (401/429/safety blocks) surface here and map to the JSON error
 * contract instead of truncating a stream.
 *
 * Two SDK constraints shape this: a result exposes a single-consumption
 * stream (touching partialObjectStream would lock out the text), and the
 * text/partial transforms swallow error chunks — so the first chunk is read
 * from fullStream, where error parts arrive as values and are rethrown
 * explicitly. The remainder is pumped from the same iterator; only text
 * deltas travel the wire, exactly like toTextStreamResponse.
 */
async function streamFirstChunkResponse(
  result: { fullStream: AsyncIterable<FullStreamPart> },
  headers: Record<string, string>,
): Promise<Response> {
  const iterator = result.fullStream[Symbol.asyncIterator]();
  const first = await iterator.next();
  if (!first.done && first.value?.type === 'error') {
    throw first.value.error;
  }
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        if (!first.done && first.value?.type === 'text-delta' && first.value.textDelta) {
          controller.enqueue(encoder.encode(first.value.textDelta));
        }
        for (;;) {
          const next = await iterator.next();
          if (next.done) break;
          if (next.value?.type === 'text-delta' && next.value.textDelta) {
            controller.enqueue(encoder.encode(next.value.textDelta));
          } else if (next.value?.type === 'error') {
            // Mid-stream failure after a 200: write the sentinel line so the
            // client can surface the mapped error instead of a truncation.
            const mapped = mapProviderError(next.value.error);
            controller.enqueue(encoder.encode(encodeStreamError(mapped.code, mapped.message)));
            break;
          }
        }
        controller.close();
      } catch (error) {
        // Iterator throw (network drop, abort): same sentinel path.
        try {
          const mapped = mapProviderError(error);
          controller.enqueue(encoder.encode(encodeStreamError(mapped.code, mapped.message)));
          controller.close();
        } catch {
          controller.error(error);
        }
      }
    },
  });
  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8', ...headers },
  });
}

/** Respond with the whole object as a single-chunk text stream (client path is identical to streaming). */
function singleChunkResponse(value: unknown, headers: Record<string, string>): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(JSON.stringify(value)));
      controller.close();
    },
  });
  return new Response(stream, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      ...headers,
    },
  });
}

/**
 * Streaming generation pipeline (brief §8):
 * primary streamObject → fallback generateText + repair (x-qag-repaired: 1) →
 * one re-ask with Zod issues → 502 bad_model_output.
 */
export async function generateStream(input: GenerateInput): Promise<Response> {
  const { kind, body, byok, requestId } = input;
  const def: GeneratorDef<unknown, unknown> = REGISTRY[kind];

  // 2. Request validation (422, no values echoed).
  const parsed = def.requestSchema.safeParse(body);
  if (!parsed.success) {
    throw new RequestValidationError(
      parsed.error.issues.map((issue) => ({
        path: issue.path.join('.'),
        message: issue.message,
      })),
    );
  }
  const req = parsed.data;

  // 3. Suspicious-content check (warn only) + total size cap.
  const { suspicious, totalChars } = collectSuspiciousAndSize(req);
  if (totalChars > MAX_TOTAL_INPUT_CHARS) {
    throw new InputTooLargeError();
  }

  // 4–5. Prompt + model.
  const { system, user } = def.buildPrompt(req);
  const modelId = resolveModel(byok.provider, byok.tier, byok.model);
  const model = createModel(byok.provider, byok.apiKey, modelId, byok.baseUrl);
  const temperature = def.temperature ?? 0.3;

  const baseHeaders: Record<string, string> = {
    'x-qag-request-id': requestId,
    'x-qag-provider': byok.provider,
    'x-qag-model': modelId,
    'x-qag-tier': byok.tier,
    'Cache-Control': 'no-store',
    ...(suspicious ? { 'x-qag-suspicious': '1' } : {}),
  };

  const forceFallback = !PROVIDERS[byok.provider].supportsJsonMode;

  // 6. Primary path: streaming structured JSON.
  if (!forceFallback) {
    try {
      const result = streamObject({
        model,
        schema: def.outputSchema as z.ZodType,
        system,
        prompt: user,
        temperature,
        maxOutputTokens: 8192,
      });
      return await streamFirstChunkResponse(result, baseHeaders);
    } catch (error) {
      if (!isJsonModeUnsupported(error)) throw error;
      // fall through to the fallback path
    }
  }

  // 7. Fallback path: plain text + extract/repair/parse.
  const startedAt = Date.now();
  const fallbackPrompt = `${user}\n\nRespond with ONLY the JSON object.`;
  const textResult = await generateText({
    model,
    system,
    prompt: fallbackPrompt,
    temperature,
    maxOutputTokens: 8192,
  });
  const rawText = textResult.text;

  let value: unknown;
  try {
    value = repairAndParse(rawText, def.outputSchema as z.ZodType).value;
  } catch (firstError) {
    // 8. Re-ask path: one more attempt with the Zod issues appended.
    const issues = formatIssues(
      firstError instanceof Error && firstError.cause ? firstError.cause : firstError,
    );
    const second = await generateText({
      model,
      system,
      prompt: fallbackPrompt + reAskSuffix(issues, rawText),
      temperature,
      maxOutputTokens: 8192,
    });
    const secondText = second.text;
    try {
      value = repairAndParse(secondText, def.outputSchema as z.ZodType).value;
    } catch {
      throw new BadModelOutputError(secondText);
    }
  }

  return singleChunkResponse(value, {
    ...baseHeaders,
    'x-qag-repaired': '1',
    'x-qag-latency-ms': String(Date.now() - startedAt),
  });
}
