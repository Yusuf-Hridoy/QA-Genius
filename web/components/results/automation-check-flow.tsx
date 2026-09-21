'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { AutomationRequest } from '@/lib/generators/automation-script/request';
import { AutomationScript } from '@/lib/generators/automation-script/schema';
import { automationFiles, downloadAutomationZip } from '@/lib/exports/zip';
import { projectSlug } from '@/lib/exports/download';
import {
  countErrors,
  countWarnings,
  runSyntaxCheck,
  summarizeReports,
  type FileReport,
} from '@/lib/automation/syntax-check';
import { checkAndRepairOnce } from '@/lib/automation/repair';
import {
  getSyntaxSummary,
  hashJson,
  setSyntaxSummary,
  type SyntaxBadge,
  type SyntaxSummary,
} from '@/lib/automation/syntax-store';
import { useKeysStore } from '@/lib/store/keys';
import { useProjectStore } from '@/lib/store/project';
import { useDefaultKey } from '@/components/shell/key-badge';
import { AutomationResult, type AutomationFileDiagnostic } from './automation-result';
import { AutomationStatusPill } from './automation-status-pill';
import { AutomationDiagnostics } from './automation-diagnostics';
import { Button } from '@/components/ui/button';

const SYNTAX_KIND = 'automation_script';

type CycleResult = {
  summary: SyntaxSummary;
  repairedScript?: AutomationScript;
};

/** In-flight check+repair cycles by output hash (StrictMode-safe: joins, never doubles). */
const inflight = new Map<string, Promise<CycleResult>>();
/** Output hashes for which the single repair POST already happened. */
const repairAttempted = new Set<string>();
/** Output hashes shown display-only while their request had not arrived yet. */
const displayOnlyKeys = new Set<string>();

/**
 * Automation result with syntax check and one auto-repair. Renders through
 * GeneratorScreen's renderResult slot; the page adopts repaired output via
 * onRepaired (sessionStorage + remount, so exports follow it).
 */
export function AutomationCheckFlow({
  data,
  isLoading,
  inputEntry,
  onRepaired,
}: {
  data: Record<string, unknown> | undefined;
  isLoading: boolean;
  /** Last valid request keyed by the output hash (arrives via onResult). */
  inputEntry: { key: string; input: Record<string, unknown> } | undefined;
  onRepaired: (script: AutomationScript) => void;
}) {
  const defaultKey = useDefaultKey();
  const tier = useKeysStore((s) => s.tier);
  const projectName = useProjectStore((s) => s.project.name);

  const [badge, setBadge] = useState<SyntaxBadge | null>(null);
  const [reports, setReports] = useState<FileReport[]>([]);
  const [beforeErrors, setBeforeErrors] = useState<number | undefined>(undefined);
  const [original, setOriginal] = useState<AutomationScript | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<{ file: string; line: number } | null>(null);
  const notified = useRef(new Set<string>());

  const script = useMemo(() => (data ? AutomationScript.safeParse(data) : null), [data]);
  const frameworkName = useMemo(() => {
    const entryInput = inputEntry?.input;
    const fromInput = typeof entryInput?.framework === 'string' ? entryInput.framework : undefined;
    return fromInput ?? script?.data?.framework ?? '';
  }, [inputEntry, script]);

  // The request that produced the current output (matched by output hash, so a
  // stale request from an earlier run is never used for the repair body).
  const usableInput = useMemo(() => {
    if (!data || !inputEntry || inputEntry.key !== hashJson(data)) return undefined;
    const parsed = AutomationRequest.safeParse(inputEntry.input);
    return parsed.success ? parsed.data : undefined;
  }, [data, inputEntry]);

  useEffect(() => {
    if (isLoading) {
      setBadge({ status: 'checking' });
      return;
    }
    if (!data || !script?.success) {
      setBadge(null);
      setReports([]);
      setBeforeErrors(undefined);
      setOriginal(null);
      return;
    }
    const current = script.data;
    const key = hashJson(data);
    let cancelled = false;

    const apply = (summary: SyntaxSummary, repairedScript?: AutomationScript) => {
      if (cancelled) return;
      setBadge(summary.badge);
      setReports(summary.reports);
      setBeforeErrors(summary.beforeErrors > 0 ? summary.beforeErrors : undefined);
      setOriginal(summary.original ?? null);
      if (repairedScript && !notified.current.has(key)) {
        notified.current.add(key);
        onRepaired(repairedScript);
      }
    };

    // Adopted repaired output: the stored summary already describes it.
    const stored = getSyntaxSummary(SYNTAX_KIND);
    if (stored && stored.outputHash === key) {
      apply(stored);
      return;
    }

    // A settled cycle is already in flight for this output: join it.
    const running = inflight.get(key);
    if (running) {
      void running.then(({ summary, repairedScript }) => apply(summary, repairedScript));
      return () => {
        cancelled = true;
      };
    }

    // This output already used its single repair attempt: display-only check.
    if (repairAttempted.has(key)) {
      setBadge({ status: 'checking' });
      void runSyntaxCheck(
        automationFiles(current).map(([name, code]) => ({ name, code })),
        frameworkName,
      ).then((fresh) => {
        if (cancelled) return;
        const status = summarizeReports(fresh);
        setReports(fresh);
        setBeforeErrors(undefined);
        if (status === 'unchecked') {
          setBadge({
            status: 'unchecked',
            python: fresh.some((r) => r.language === 'python'),
          });
        } else if (status === 'clean') {
          setBadge({ status: 'clean', warnings: countWarnings(fresh) });
        } else {
          setBadge({
            status: 'errors',
            errors: countErrors(fresh),
            warnings: countWarnings(fresh),
          });
        }
      });
      return () => {
        cancelled = true;
      };
    }

    // The request arrives via onResult after the streamed object completes,
    // so the first run may only check for display; the re-run (inputEntry
    // dep) upgrades to the full cycle once the matching request arrives.
    if (!usableInput || !defaultKey) {
      if (displayOnlyKeys.has(key)) return;
      displayOnlyKeys.add(key);
      // No valid request to repair with: check for display only.
      setBadge({ status: 'checking' });
      void runSyntaxCheck(
        automationFiles(current).map(([name, code]) => ({ name, code })),
        frameworkName,
      ).then((fresh) => {
        if (cancelled || inflight.has(key)) return;
        const status = summarizeReports(fresh);
        const errors = countErrors(fresh);
        const warnings = countWarnings(fresh);
        setReports(fresh);
        setBeforeErrors(undefined);
        if (status === 'unchecked') {
          setBadge({
            status: 'unchecked',
            python: fresh.some((r) => r.language === 'python'),
          });
        } else {
          setBadge(
            status === 'clean'
              ? { status: 'clean', warnings }
              : { status: 'errors', errors, warnings },
          );
        }
        if (!getSyntaxSummary(SYNTAX_KIND) || getSyntaxSummary(SYNTAX_KIND)?.outputHash !== key) {
          setSyntaxSummary(SYNTAX_KIND, {
            badge:
              status === 'unchecked'
                ? { status: 'unchecked', python: fresh.some((r) => r.language === 'python') }
                : status === 'clean'
                  ? { status: 'clean', warnings }
                  : { status: 'errors', errors, warnings },
            beforeErrors: 0,
            afterErrors: errors,
            warnings,
            reports: fresh,
            outputHash: key,
          });
        }
      });
      return () => {
        cancelled = true;
      };
    }
    displayOnlyKeys.delete(key);

    // Full cycle: check, at most one repair, re-check.
    setBadge({ status: 'checking' });
    const cycle = (async (): Promise<CycleResult> => {
      const result = await checkAndRepairOnce({
        script: current,
        framework: frameworkName,
        input: usableInput,
        defaultKey,
        tier,
        check: (files, fw) => runSyntaxCheck(files, fw),
        onStage: (stage) => {
          if (!cancelled)
            setBadge(stage === 'repair' ? { status: 'repairing' } : { status: 'checking' });
        },
      });
      if (result.repairAttempted) repairAttempted.add(key);
      const summary: SyntaxSummary = {
        badge: result.badge,
        beforeErrors: result.beforeErrors,
        afterErrors: result.afterErrors,
        warnings: result.warnings,
        reports: result.reports,
        outputHash: result.repairedScript ? hashJson(result.repairedScript) : key,
        ...(result.repairedScript
          ? { repairedHash: hashJson(result.repairedScript), original: current }
          : {}),
      };
      setSyntaxSummary(SYNTAX_KIND, summary);
      return { summary, repairedScript: result.repairedScript };
    })();
    inflight.set(key, cycle);
    void cycle
      .then(({ summary, repairedScript }) => {
        inflight.delete(key);
        apply(summary, repairedScript);
      })
      .catch(() => {
        inflight.delete(key);
      });
    return () => {
      cancelled = true;
    };
  }, [
    data,
    isLoading,
    inputEntry,
    defaultKey,
    tier,
    frameworkName,
    onRepaired,
    script,
    usableInput,
  ]);

  const fileDiagnostics = useMemo<Record<string, AutomationFileDiagnostic>>(() => {
    const map: Record<string, AutomationFileDiagnostic> = {};
    for (const r of reports) {
      map[r.name] = { errors: r.errors.length, warnings: r.warnings.length, checked: r.checked };
    }
    return map;
  }, [reports]);

  const selectRow = (file: string, line: number) => {
    setSelectedFile(file);
    setHighlight({ file, line });
  };

  return (
    <div className="flex flex-col gap-3">
      {badge ? (
        <div className="flex flex-wrap items-center gap-2" data-testid="automation-syntax-badge">
          <AutomationStatusPill badge={badge} />
          {original ? (
            <Button
              variant="ghost"
              onClick={() => void downloadAutomationZip(original, projectSlug(projectName))}
            >
              Download original
            </Button>
          ) : null}
        </div>
      ) : null}
      <AutomationResult
        data={data}
        isLoading={isLoading}
        fileDiagnostics={reports.length > 0 ? fileDiagnostics : undefined}
        highlightFile={highlight?.file}
        highlightLines={highlight ? [highlight.line] : undefined}
        selectedFile={selectedFile}
        onSelectFile={(name) => {
          setSelectedFile(name);
          if (highlight && highlight.file !== name) setHighlight(null);
        }}
      />
      <AutomationDiagnostics
        reports={reports}
        beforeErrors={beforeErrors}
        onSelectRow={selectRow}
      />
    </div>
  );
}
