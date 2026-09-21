'use client';

import { useMemo, useState } from 'react';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';
import { automationFiles } from '@/lib/exports/zip';
import { Card, CardHeader } from '@/components/ui/card';
import { CodeBlock } from '@/components/ui/code-block';
import { Pill } from '@/components/ui/pill';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils/cn';
import { arr, str } from './partial-data';
import type { ResultProps } from './types';

function languageFor(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  switch (ext) {
    case 'ts':
      return 'ts';
    case 'js':
    case 'jsx':
      return 'js';
    case 'py':
      return 'python';
    case 'json':
      return 'json';
    case 'ini':
    case 'cfg':
    case 'toml':
      return 'ini';
    default:
      return 'text';
  }
}

function AutomationSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-24 rounded-full" />
        <Skeleton className="h-5 w-40" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="h-72 w-56 shrink-0" />
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}

export type AutomationFileDiagnostic = {
  errors: number;
  warnings: number;
  checked: boolean;
};

export function AutomationResult({
  data,
  isLoading,
  fileDiagnostics,
  highlightFile,
  highlightLines,
  selectedFile,
  onSelectFile,
}: ResultProps & {
  /** Per-file syntax state for the tree dots (absent = no dots). */
  fileDiagnostics?: Record<string, AutomationFileDiagnostic>;
  /** File whose lines are highlighted in the code viewer. */
  highlightFile?: string | null;
  /** 1-based lines highlighted in the active file. */
  highlightLines?: number[];
  /** Controlled file selection (defaults to internal state). */
  selectedFile?: string | null;
  onSelectFile?: (name: string) => void;
}) {
  const [internalSelected, setInternalSelected] = useState<string | null>(null);

  const framework = str(data?.framework);
  const setupInstructions = arr<string>(data?.setup_instructions);
  const executionCommand = str(data?.execution_command);
  const designNotes = str(data?.design_notes);
  const projectStructure = arr<string>(data?.project_structure);

  // Files as they would be exported (name → content).
  const files = useMemo<[string, string][]>(() => {
    if (!data) return [];
    return automationFiles(data as unknown as AutomationScript);
  }, [data]);

  const activeFile =
    files.find(([name]) => name === (selectedFile ?? internalSelected)) ?? files[0];

  const selectFile = (name: string) => {
    setInternalSelected(name);
    onSelectFile?.(name);
  };

  if (!data) {
    return isLoading ? <AutomationSkeleton /> : null;
  }

  return (
    <div className="flex flex-col gap-3" data-testid="automation-result">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-[15px] font-semibold">Automation project</h2>
        {framework ? <Pill tone="info">{framework}</Pill> : null}
        {data.structure ? <Pill tone="neutral">{str(data.structure)}</Pill> : null}
      </div>

      <div className="flex flex-col gap-3 md:flex-row">
        <div className="w-full shrink-0 md:w-60">
          <Card className="p-2.5">
            <h3 className="px-1.5 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
              Project structure
            </h3>
            <ul className="flex flex-col gap-0.5">
              {(files.length > 0 ? files.map(([name]) => name) : projectStructure).map(
                (name, i) => {
                  const isFile = files.some(([fileName]) => fileName === name);
                  const isActive = activeFile?.[0] === name;
                  const diag = fileDiagnostics?.[name];
                  const dotTone =
                    !diag || !diag.checked ? 'neutral' : diag.errors > 0 ? 'bad' : 'ok';
                  const dotTitle = !diag
                    ? undefined
                    : !diag.checked
                      ? 'not checked'
                      : `${diag.errors} error${diag.errors === 1 ? '' : 's'}, ${diag.warnings} warning${diag.warnings === 1 ? '' : 's'}`;
                  return (
                    <li key={`${name}-${i}`}>
                      <button
                        type="button"
                        disabled={!isFile}
                        onClick={() => selectFile(name)}
                        aria-current={isActive ? 'true' : undefined}
                        title={dotTitle}
                        className={cn(
                          'flex w-full items-center gap-1.5 truncate rounded-[var(--qg-radius)] px-2 py-1.5 text-left font-mono text-[12px] transition-colors duration-[var(--qg-dur)]',
                          isActive
                            ? 'bg-accent-soft text-accent'
                            : isFile
                              ? 'text-text-2 hover:bg-card-2'
                              : 'text-muted',
                        )}
                      >
                        {fileDiagnostics ? (
                          <span
                            aria-hidden
                            title={dotTitle}
                            className={cn(
                              'h-1.5 w-1.5 shrink-0 rounded-full',
                              dotTone === 'ok' && 'bg-ok-fg',
                              dotTone === 'bad' && 'bg-bad-fg',
                              dotTone === 'neutral' && 'bg-border-strong',
                            )}
                          />
                        ) : null}
                        <span className="truncate">{name}</span>
                      </button>
                    </li>
                  );
                },
              )}
              {files.length === 0 && projectStructure.length === 0 && isLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : null}
            </ul>
          </Card>
        </div>
        <div className="min-w-0 flex-1">
          {activeFile ? (
            <CodeBlock
              code={activeFile[1]}
              language={languageFor(activeFile[0])}
              filename={activeFile[0]}
              highlightLines={highlightFile === activeFile[0] ? highlightLines : undefined}
              scrollToLine={highlightFile === activeFile[0] ? highlightLines?.[0] : undefined}
            />
          ) : (
            <Skeleton className="h-72 w-full" />
          )}
        </div>
      </div>

      {setupInstructions.length > 0 ? (
        <Card>
          <CardHeader title="Setup" />
          <ol className="list-decimal pl-5 font-mono text-[12px] text-text-2">
            {setupInstructions.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </Card>
      ) : null}

      {executionCommand ? (
        <Card>
          <CardHeader title="Run" />
          <CodeBlock code={executionCommand} language="bash" filename="terminal" />
        </Card>
      ) : null}

      {designNotes ? (
        <details className="rounded-[var(--qg-radius-card)] border border-border bg-card px-4 py-3">
          <summary className="cursor-pointer text-[13px] font-medium">Design notes</summary>
          <p className="mt-2 text-[13px] leading-[1.7] text-text-2">{designNotes}</p>
        </details>
      ) : null}
    </div>
  );
}
