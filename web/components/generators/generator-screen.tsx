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

function resultStorageKey(kind: GeneratorKind) {
  return `qag.result.${kind}`;
}

export function GeneratorScreen({ kind }: { kind: GeneratorKind }) {
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
  const suspiciousToastShown = useRef(false);

  // Restore the last result of this kind from sessionStorage (survives tab switches).
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(resultStorageKey(kind));
      if (raw) setObject(JSON.parse(raw) as Record<string, unknown>);
    } catch {
      // corrupted session entry — ignore
    }
    setRestored(true);
  }, [kind, setObject]);

  // Persist the latest completed result.
  useEffect(() => {
    if (!restored || isLoading || !object) return;
    try {
      sessionStorage.setItem(resultStorageKey(kind), JSON.stringify(object));
    } catch {
      // storage full — ignore
    }
  }, [object, isLoading, kind, restored]);

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

  const generate = useCallback(async () => {
    const parsed = (def.requestSchema as { safeParse: (v: unknown) => unknown }).safeParse(values);
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
  }, [def, values, defaultKey, tier, submit]);

  const hasResult = object !== undefined;
  const latencySeconds = meta.latencyMs !== undefined ? (meta.latencyMs / 1000).toFixed(1) : null;

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <div className="w-full shrink-0 lg:w-[380px]">
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
            <ui.Result data={object} isLoading={isLoading} />
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
          </div>
        )}
      </div>

      <div aria-live="polite" role="status" className="sr-only">
        {isLoading ? 'Generating…' : error ? error.message : hasResult ? 'Done' : ''}
      </div>
    </div>
  );
}
