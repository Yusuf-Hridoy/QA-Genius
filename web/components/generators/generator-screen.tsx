'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Square } from 'lucide-react';
import { REGISTRY, type GeneratorKind } from '@/lib/generators/kinds';
import { buildByokHeaders } from '@/lib/llm/byok';
import { useKeysStore } from '@/lib/store/keys';
import { useObjectStream } from '@/lib/client/use-object-stream';
import { showApiErrorToast, showNoKeyToast, showSuspiciousToast } from '@/lib/client/api-error';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/pill';
import { EmptyState } from '@/components/ui/empty-state';
import { useDefaultKey } from '@/components/shell/key-badge';
import { GENERATOR_UI, type GeneratorUi } from './registry';
import type { StreamMeta } from '@/lib/client/use-object-stream';
import type { ReactNode } from 'react';

function resultStorageKey(kind: GeneratorKind) {
  return `qag.result.${kind}`;
}

export function GeneratorScreen({
  kind,
  initialValues,
  onResult,
  autoSubmitOnMount,
  formSummary,
  resultHeader,
  renderResult,
  resultFooter,
  restoredResult,
}: {
  kind: GeneratorKind;
  /** Prefill the form (e.g. pipeline handoffs). Applied on mount and when kind changes. */
  initialValues?: Record<string, unknown>;
  /** Called with the completed output, its input, and the stream meta. */
  onResult?: (
    output: Record<string, unknown>,
    input: Record<string, unknown>,
    meta: StreamMeta,
  ) => void;
  /** When set, this request is submitted once automatically after mount. */
  autoSubmitOnMount?: Record<string, unknown>;
  /** When set, the form collapses behind a summary bar with an edit toggle. */
  formSummary?: ReactNode;
  /** Rendered above the result card (pipeline extras: coverage, duel, refine). */
  resultHeader?: ReactNode;
  /** Replaces the default result component (for pipeline result extensions). */
  renderResult?: (args: {
    data: Record<string, unknown> | undefined;
    isLoading: boolean;
  }) => ReactNode;
  /** Rendered below the exports row. */
  resultFooter?: ReactNode;
  /**
   * Pipeline fallback: when this kind has no session result (e.g. a run
   * adopted from a share link), restore this accepted output instead.
   */
  restoredResult?: Record<string, unknown>;
}) {
  const ui: GeneratorUi = GENERATOR_UI[kind];
  const def = REGISTRY[kind];
  const defaultKey = useDefaultKey();
  const tier = useKeysStore((s) => s.tier);

  const { object, submit, isLoading, error, stop, meta, stopped, setObject } = useObjectStream<
    Record<string, unknown>
  >(`/api/generate/${kind}`);

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [lastInput, setLastInput] = useState<Record<string, unknown>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [restored, setRestored] = useState(false);
  const [reported, setReported] = useState<Record<string, unknown> | undefined>(undefined);
  const [formOpen, setFormOpen] = useState(() => formSummary === undefined);
  const suspiciousToastShown = useRef(false);
  const autoSubmitted = useRef(false);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  // Restore the last result of this kind from sessionStorage (survives tab switches).
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = sessionStorage.getItem(resultStorageKey(kind));
      if (stored) setObject(JSON.parse(stored) as Record<string, unknown>);
    } catch {
      // corrupted session entry — ignore
    }
    if (!stored && restoredResult) setObject(restoredResult);
    if (initialValues) {
      setValues({ ...initialValues });
      setFieldErrors({});
    }
    // Pipeline summary-bar mode: start collapsed when there is already a
    // result (or an auto-submit is on its way); otherwise show the form.
    if (formSummary !== undefined) {
      setFormOpen(autoSubmitOnMount !== undefined ? false : !(stored || restoredResult));
    }
    setReported(undefined);
    setRestored(true);
    // initialValues/restoredResult are intentionally applied on mount/kind change only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, setObject]);

  // Pipeline handoff: submit the provided request once after mount.
  useEffect(() => {
    if (!autoSubmitOnMount || autoSubmitted.current || !restored) return;
    autoSubmitted.current = true;
    setValues({ ...autoSubmitOnMount });
    setFieldErrors({});
    if (formSummary !== undefined) setFormOpen(false);
    void generateWith(autoSubmitOnMount);
    // Runs once per mount by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSubmitOnMount, restored]);

  // Persist the latest completed result.
  useEffect(() => {
    if (!restored || isLoading || !object) return;
    try {
      sessionStorage.setItem(resultStorageKey(kind), JSON.stringify(object));
    } catch {
      // storage full — ignore
    }
    // Notify the pipeline (or other owner) once per completed result object.
    if (onResultRef.current && object !== reported) {
      setReported(object);
      onResultRef.current(object, lastInput, meta);
    }
  }, [object, isLoading, kind, restored, meta, lastInput, reported]);

  // Suspicious-input warning comes from the x-qag-suspicious response header.
  useEffect(() => {
    if (meta.suspicious && !suspiciousToastShown.current) {
      suspiciousToastShown.current = true;
      showSuspiciousToast();
    }
    if (!meta.suspicious) suspiciousToastShown.current = false;
  }, [meta.suspicious]);

  // Surface errors as toasts; the previous result (if any) stays on screen.
  useEffect(() => {
    if (error) showApiErrorToast(error);
  }, [error]);

  const onField = useCallback((field: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setFieldErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  const onLoadExample = useCallback(() => {
    setValues({ ...ui.example });
    setFieldErrors({});
  }, [ui.example]);

  const generateWith = useCallback(
    async (inputValues: Record<string, unknown>) => {
      const parsed = (def.requestSchema as { safeParse: (v: unknown) => unknown }).safeParse(
        inputValues,
      );
      // Client-side validation first: show inline field errors (Generate is never disabled).
      const result = parsed as {
        success: boolean;
        data?: unknown;
        error?: { issues: { path: (string | number)[]; message: string }[] };
      };
      if (!result.success) {
        const errors: Record<string, string> = {};
        for (const issue of result.error?.issues ?? []) {
          const key = issue.path.join('.');
          if (!(key in errors)) errors[key] = issue.message;
        }
        setFieldErrors(errors);
        return;
      }
      if (!defaultKey) {
        showNoKeyToast();
        return;
      }
      setLastInput(result.data as Record<string, unknown>);
      await submit(result.data, buildByokHeaders(defaultKey, tier));
    },
    [def, defaultKey, tier, submit],
  );

  const generate = useCallback(async () => {
    await generateWith(values);
  }, [generateWith, values]);

  const hasResult = object !== undefined;
  const latencySeconds = meta.latencyMs !== undefined ? (meta.latencyMs / 1000).toFixed(1) : null;

  const formCollapsed = formSummary !== undefined && !formOpen;

  return (
    <div
      className={
        formCollapsed ? 'flex flex-col gap-4' : 'flex flex-col gap-4 lg:flex-row lg:items-start'
      }
    >
      {formCollapsed ? (
        <div className="w-full rounded-[var(--qg-radius-card)] border border-border bg-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[13px] text-text-2">{formSummary}</p>
            <Button variant="secondary" onClick={() => setFormOpen(true)}>
              Edit inputs
            </Button>
          </div>
        </div>
      ) : (
        <div className="w-full shrink-0 lg:w-[380px]">
          {formSummary !== undefined ? (
            <div className="mb-2 flex items-center justify-end">
              <Button variant="ghost" onClick={() => setFormOpen(false)}>
                Hide inputs
              </Button>
            </div>
          ) : null}
          <ui.Form value={values} errors={fieldErrors} onField={onField} />
          <div className="mt-4 flex items-center gap-2">
            {isLoading ? (
              <Button variant="secondary" onClick={stop} aria-label="Stop generating">
                <Square className="h-3.5 w-3.5" aria-hidden />
                Stop
              </Button>
            ) : (
              <Button variant="primary" onClick={generate}>
                Generate
              </Button>
            )}
          </div>
        </div>
      )}

      <div className="min-w-0 flex-1">
        {!hasResult && !isLoading ? (
          <EmptyState
            icon={ui.emptyIcon}
            headline={ui.emptyHeadline}
            description={ui.emptyDescription}
            action={{ label: 'Load example', onClick: onLoadExample }}
          />
        ) : (
          <div className="flex flex-col gap-3">
            {resultHeader}
            {renderResult ? (
              renderResult({ data: object, isLoading })
            ) : (
              <ui.Result data={object} isLoading={isLoading} />
            )}
            {(hasResult || isLoading) && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-[12px] text-muted">
                  {meta.model ?? '…'} · {meta.tier ?? tier}
                  {latencySeconds !== null ? ` · ${latencySeconds}s` : ''}
                  {meta.requestId ? ` · request ${meta.requestId.slice(0, 4)}…` : ''}
                  {stopped ? ' · stopped' : ''}
                </p>
                {meta.repaired ? <Pill tone="neutral">repaired output</Pill> : null}
              </div>
            )}
            {hasResult && !isLoading && <ui.Exports data={object} input={lastInput} />}
            {resultFooter}
          </div>
        )}
      </div>

      <div aria-live="polite" role="status" className="sr-only">
        {isLoading ? 'Generating…' : error ? error.message : hasResult ? 'Done' : ''}
      </div>
    </div>
  );
}
