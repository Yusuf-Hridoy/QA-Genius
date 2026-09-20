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

export function AutomationResult({ data, isLoading }: ResultProps) {
  const [selected, setSelected] = useState<string | null>(null);

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

  const activeFile = files.find(([name]) => name === selected) ?? files[0];

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
                  return (
                    <li key={`${name}-${i}`}>
                      <button
                        type="button"
                        disabled={!isFile}
                        onClick={() => setSelected(name)}
                        aria-current={isActive ? 'true' : undefined}
                        className={cn(
                          'w-full truncate rounded-[var(--radius)] px-2 py-1.5 text-left font-mono text-[12px] transition-colors duration-[var(--dur)]',
                          isActive
                            ? 'bg-accent-soft text-accent'
                            : isFile
                              ? 'text-text-2 hover:bg-card-2'
                              : 'text-muted',
                        )}
                      >
                        {name}
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
        <details className="rounded-[var(--radius-card)] border border-border bg-card px-4 py-3">
          <summary className="cursor-pointer text-[13px] font-medium">Design notes</summary>
          <p className="mt-2 text-[13px] leading-[1.7] text-text-2">{designNotes}</p>
        </details>
      ) : null}
    </div>
  );
}
