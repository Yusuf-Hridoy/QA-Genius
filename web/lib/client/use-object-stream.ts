'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { parsePartialJson } from './parse-partial-json';
import { decodeStreamError } from '@/lib/llm/stream-error';

export type StreamMeta = {
  provider?: string;
  model?: string;
  tier?: string;
  requestId?: string;
  repaired?: boolean;
  suspicious?: boolean;
  latencyMs?: number;
};

export type ApiError = Error & {
  code?: string;
  details?: Record<string, unknown>;
  status?: number;
};

/** Minimal shape of the kind's Zod output schema, for final validation. */
export type FinalObjectSchema = {
  safeParse(data: unknown): { success: boolean };
};

function badModelOutput(): ApiError {
  const error = new Error(
    "The model returned output that couldn't be read. Try again or switch tier.",
  ) as ApiError;
  error.code = 'bad_model_output';
  error.status = 502;
  return error;
}

/**
 * Client for POST /api/generate/[kind]. Replaces the AI SDK's useObject
 * (removed in ai v7): consumes the partial-JSON text stream and updates
 * state progressively. BYOK headers go in fetch headers, never the body.
 * When a schema is provided, the final object is validated after the stream
 * closes; invalid output (or no chunks at all) surfaces bad_model_output.
 */
export function useObjectStream<T>(api: string, schema?: FinalObjectSchema) {
  const [object, setObject] = useState<T | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [meta, setMeta] = useState<StreamMeta>({});
  const [stopped, setStopped] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const submit = useCallback(
    async (body: unknown, headers: Record<string, string>) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);
      setStopped(false);
      setError(null);
      // Keep the previous result on screen until the new stream yields its
      // first parsed chunk — on error the last result stays visible (§4.5).
      setMeta({});
      const startedAt = performance.now();

      try {
        const response = await fetch(api, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        const responseMeta: StreamMeta = {
          provider: response.headers.get('x-qag-provider') ?? undefined,
          model: response.headers.get('x-qag-model') ?? undefined,
          tier: response.headers.get('x-qag-tier') ?? undefined,
          requestId: response.headers.get('x-qag-request-id') ?? undefined,
          repaired: response.headers.get('x-qag-repaired') === '1',
          suspicious: response.headers.get('x-qag-suspicious') === '1',
        };

        if (!response.ok || !response.body) {
          const data: unknown = await response.json().catch(() => null);
          const parsed =
            data && typeof data === 'object'
              ? (data as { error?: string; message?: string; details?: Record<string, unknown> })
              : {};
          const apiError = new Error(
            parsed.message ?? 'Something went wrong. Try again.',
          ) as ApiError;
          apiError.code = parsed.error;
          apiError.details = parsed.details;
          apiError.status = response.status;
          setError(apiError);
          setMeta(responseMeta);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = '';
        let streamError: { code?: string; message?: string } | null = null;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          accumulated += decoder.decode(value, { stream: true });
          // Mid-stream provider error: strip the sentinel before parsing.
          const split = decodeStreamError(accumulated);
          if (split.code) {
            streamError = { code: split.code, message: split.message };
            const partial = parsePartialJson(split.jsonText);
            if (partial !== undefined) {
              setObject(partial as T);
            }
            break;
          }
          const partial = parsePartialJson(split.jsonText);
          if (partial !== undefined) {
            setObject(partial as T);
          }
        }
        if (!controller.signal.aborted) {
          if (streamError?.code) {
            const apiError = new Error(
              streamError.message ?? 'Your provider failed mid-stream. Try again.',
            ) as ApiError;
            apiError.code = streamError.code;
            setError(apiError);
          } else {
            const { jsonText } = decodeStreamError(accumulated);
            const finalObject = parsePartialJson(jsonText);
            const valid =
              finalObject !== undefined &&
              (schema === undefined || schema.safeParse(finalObject).success);
            if (!valid) {
              setError(badModelOutput());
            }
          }
        }
        setMeta({ ...responseMeta, latencyMs: Math.round(performance.now() - startedAt) });
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') {
          setStopped(true);
        } else {
          setError(e as ApiError);
        }
      } finally {
        setIsLoading(false);
      }
    },
    [api, schema],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setStopped(true);
  }, []);

  // abort on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return { object, submit, isLoading, error, stop, meta, stopped, setObject };
}
