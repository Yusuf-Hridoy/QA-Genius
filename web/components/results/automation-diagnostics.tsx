'use client';

import type { FileReport } from '@/lib/automation/syntax-check';

/**
 * Collapsible diagnostics table under the Automation code viewer. Clicking a
 * row selects the file and highlights the line in the code viewer.
 */
export function AutomationDiagnostics({
  reports,
  beforeErrors,
  onSelectRow,
}: {
  reports: FileReport[];
  /** Error count before the repair attempt; shown as a before → after line. */
  beforeErrors?: number;
  onSelectRow: (file: string, line: number) => void;
}) {
  const checked = reports.filter((r) => r.checked);
  const errors = checked.flatMap((r) => r.errors.map((e) => ({ file: r.name, ...e })));
  const warnings = checked.flatMap((r) => r.warnings.map((w) => ({ file: r.name, ...w })));
  const repairedClean = (beforeErrors ?? 0) > 0 && errors.length === 0 && warnings.length === 0;
  if (errors.length === 0 && warnings.length === 0 && !repairedClean) return null;

  const afterErrors = errors.length;
  const showBeforeAfter = (beforeErrors ?? 0) > 0 && (beforeErrors ?? 0) !== afterErrors;

  return (
    <details
      className="rounded-[var(--qg-radius-card)] border border-border bg-card px-4 py-3"
      open={errors.length > 0 || (beforeErrors ?? 0) > 0}
      data-testid="automation-diagnostics"
    >
      <summary className="cursor-pointer text-[13px] font-medium">
        Syntax diagnostics
        {repairedClean ? (
          <span className="ml-2 font-mono text-[12px] text-muted">{beforeErrors} → 0 errors</span>
        ) : showBeforeAfter ? (
          <span className="ml-2 font-mono text-[12px] text-muted">
            {beforeErrors} → {afterErrors} errors
          </span>
        ) : (
          <span className="ml-2 font-mono text-[12px] text-muted">
            {errors.length} errors
            {warnings.length > 0 ? `, ${warnings.length} warnings` : ''}
          </span>
        )}
      </summary>
      <ul className="mt-2 flex flex-col gap-0.5">
        {errors.map((d, i) => (
          <li key={`e-${i}`}>
            <button
              type="button"
              onClick={() => onSelectRow(d.file, d.line)}
              className="w-full truncate rounded-[var(--qg-radius)] px-2 py-1 text-left font-mono text-[12px] text-bad-fg hover:bg-card-2"
              title={`${d.file}:${d.line}:${d.column} — ${d.message}`}
            >
              {d.file}:{d.line}:{d.column} — {d.message}
            </button>
          </li>
        ))}
        {warnings.map((d, i) => (
          <li key={`w-${i}`}>
            <button
              type="button"
              onClick={() => onSelectRow(d.file, d.line)}
              className="w-full truncate rounded-[var(--qg-radius)] px-2 py-1 text-left font-mono text-[12px] text-warn-fg hover:bg-card-2"
              title={`${d.file}:${d.line}:${d.column} — ${d.message}`}
            >
              {d.file}:{d.line}:{d.column} — {d.message}
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
