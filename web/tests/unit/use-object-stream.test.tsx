import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useObjectStream } from '@/lib/client/use-object-stream';

function streamResponse(payload: string, headers: Record<string, string> = {}): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { headers },
  );
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useObjectStream', () => {
  it('streams a partial-JSON object and records meta headers', async () => {
    fetchMock.mockResolvedValue(
      streamResponse('{"test_cases":[{"id":"TC-001"}]}', {
        'x-qag-provider': 'gemini',
        'x-qag-model': 'gemini-2.5-flash-lite',
        'x-qag-request-id': 'req-abc',
      }),
    );
    const { result } = renderHook(() => useObjectStream('/api/generate/test_cases'));

    await act(async () => {
      await result.current.submit({}, { 'x-llm-key': 'k' });
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.object).toEqual({ test_cases: [{ id: 'TC-001' }] });
    expect(result.current.meta.provider).toBe('gemini');
    expect(result.current.meta.model).toBe('gemini-2.5-flash-lite');
    expect(result.current.meta.requestId).toBe('req-abc');
    expect(result.current.meta.latencyMs).toBeGreaterThanOrEqual(0);
    expect(result.current.error).toBeNull();
  });

  it('parses error responses into an ApiError', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: 'byok_required',
          message: 'Add an API key in Settings to generate.',
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    );
    const { result } = renderHook(() => useObjectStream('/api/generate/story_analyzer'));

    await act(async () => {
      await result.current.submit({}, {});
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.error?.code).toBe('byok_required');
    expect(result.current.error?.status).toBe(401);
  });

  it('marks the stream as stopped on abort', async () => {
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>(() => {
          // never resolves until aborted
        }),
    );
    const { result } = renderHook(() => useObjectStream('/api/generate/test_cases'));

    act(() => {
      void result.current.submit({}, {});
    });
    act(() => {
      result.current.stop();
    });

    await waitFor(() => {
      expect(result.current.stopped).toBe(true);
    });
    expect(result.current.isLoading).toBe(false);
  });

  it('surfaces bad_model_output when the final object fails the schema', async () => {
    fetchMock.mockResolvedValue(streamResponse('{"ok":false}'));
    const { result } = renderHook(() =>
      useObjectStream('/api/generate/ping', {
        safeParse: (data: unknown) => ({
          success: (data as { ok?: boolean })?.ok === true,
        }),
      }),
    );

    await act(async () => {
      await result.current.submit({}, {});
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.error?.code).toBe('bad_model_output');
    expect(result.current.error?.status).toBe(502);
  });

  it('reports no error when the final object passes the schema', async () => {
    fetchMock.mockResolvedValue(streamResponse('{"ok":true}'));
    const { result } = renderHook(() =>
      useObjectStream('/api/generate/ping', { safeParse: () => ({ success: true }) }),
    );

    await act(async () => {
      await result.current.submit({}, {});
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.object).toEqual({ ok: true });
  });
});
