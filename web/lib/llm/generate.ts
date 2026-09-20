import { generateText, streamObject } from 'ai';
import { ZodError, type z } from 'zod';
import { REGISTRY, type GeneratorKind, type GeneratorDef } from '@/lib/generators/kinds';
import { createModel, resolveModel, PROVIDERS } from './providers';
import { detectSuspicious } from './suspicious';
import { repairAndParse } from './repair';
import { isJsonModeUnsupported } from './errors';
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

function reAskSuffix(issues: string): string {
  return (
    `\n\nYour previous response was not valid JSON for the required schema. Errors:\n${issues}\n` +
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
        temperature: 0.3,
        maxOutputTokens: 8192,
      });
      return result.toTextStreamResponse({ headers: baseHeaders });
    } catch (error) {
      if (!isJsonModeUnsupported(error)) throw error;
      // fall through to the fallback path
    }
  }

  // 7. Fallback path: plain text + extract/repair/parse.
  const startedAt = Date.now();
  const fallbackPrompt = `${user}\n\nRespond with ONLY the JSON object.`;
  let rawText: string;
  try {
    const textResult = await generateText({
      model,
      system,
      prompt: fallbackPrompt,
      temperature: 0.3,
      maxOutputTokens: 8192,
    });
    rawText = textResult.text;
  } catch (error) {
    // Provider errors from the fallback surface to the caller (mapped in the route).
    throw error;
  }

  let value: unknown;
  try {
    value = repairAndParse(rawText, def.outputSchema as z.ZodType).value;
  } catch (firstError) {
    // 8. Re-ask path: one more attempt with the Zod issues appended.
    const issues = formatIssues(
      firstError instanceof Error && firstError.cause ? firstError.cause : firstError,
    );
    let secondText: string;
    try {
      const second = await generateText({
        model,
        system,
        prompt: fallbackPrompt + reAskSuffix(issues),
        temperature: 0.3,
        maxOutputTokens: 8192,
      });
      secondText = second.text;
    } catch (error) {
      throw error;
    }
    try {
      value = repairAndParse(secondText, def.outputSchema as z.ZodType).value;
      rawText = secondText;
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
