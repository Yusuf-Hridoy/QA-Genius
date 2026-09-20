'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Dialog } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/pill';
import {
  MAX_SUITE_ROWS,
  applyMapping,
  guessMapping,
  parseCsv,
  parseXlsx,
  type ColumnMapping,
  type RawTable,
} from '@/lib/suite/parse';
import { putSuite } from '@/lib/suite/db';
import { useRunStore } from '@/lib/store/run';

function MappingSelect({
  label,
  value,
  headers,
  optional,
  onChange,
}: {
  label: string;
  value: string;
  headers: string[];
  optional?: boolean;
  onChange: (header: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-[12px] font-medium">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-[var(--qg-radius)] border border-border bg-card px-2 py-1.5 text-[13px] font-normal"
      >
        {optional ? <option value="">Not mapped</option> : null}
        {headers.map((h) => (
          <option key={h} value={h}>
            {h}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Existing-suite upload: CSV/XLSX parsed client-side, column mapping with
 * preview, rows stored in IndexedDB (re-import replaces).
 */
export function SuiteUploadDialog({
  open,
  onOpenChange,
  suiteId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suiteId: string;
  onImported: () => void;
}) {
  const setSuiteSummary = useRunStore((s) => s.setSuiteSummary);
  const [fileName, setFileName] = useState('');
  const [table, setTable] = useState<RawTable | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [importing, setImporting] = useState(false);

  const reset = () => {
    setFileName('');
    setTable(null);
    setMapping(null);
    setTruncated(false);
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    reset();
    setFileName(file.name);
    try {
      const lower = file.name.toLowerCase();
      const next: RawTable = lower.endsWith('.csv')
        ? parseCsv(await file.text())
        : parseXlsx(new Uint8Array(await file.arrayBuffer()));
      if (next.records.length === 0) {
        toast.error('The file has no data rows.');
        return;
      }
      setTable(next);
      setMapping(guessMapping(next.headers));
      setTruncated(next.records.length > MAX_SUITE_ROWS);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'The file could not be read.');
    }
  };

  const preview =
    table && mapping
      ? applyMapping(table, {
          ...(mapping.id ? { id: mapping.id } : {}),
          title: mapping.title || table.headers[0] || '',
          steps: mapping.steps || table.headers[1] || '',
          expected: mapping.expected || table.headers[2] || '',
        }).rows.slice(0, 5)
      : [];

  const canImport =
    table !== null && mapping !== null && mapping.title && mapping.steps && mapping.expected;

  const onImport = async () => {
    if (!table || !mapping) return;
    setImporting(true);
    try {
      const { rows, truncated: wasTruncated } = applyMapping(table, {
        ...(mapping.id ? { id: mapping.id } : {}),
        title: mapping.title,
        steps: mapping.steps,
        expected: mapping.expected,
      });
      await putSuite({ suiteId, fileName, importedAt: new Date().toISOString(), rows });
      setSuiteSummary({ fileName, importedAt: new Date().toISOString(), count: rows.length });
      if (wasTruncated) {
        toast.error(`Import capped at ${MAX_SUITE_ROWS} rows; the rest was skipped.`);
      }
      onOpenChange(false);
      reset();
      onImported();
    } catch {
      toast.error('The suite could not be saved in this browser.');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Compare with your suite">
      <div className="flex flex-col gap-3">
        <label htmlFor="suite-file" className="text-[13px] font-medium">
          Test suite file (.csv, .xlsx, .xls)
        </label>
        <input
          id="suite-file"
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={(e) => void onFile(e.target.files?.[0])}
          className="text-[13px]"
        />
        {truncated ? (
          <Pill tone="warn">Large file: only the first {MAX_SUITE_ROWS} rows are imported.</Pill>
        ) : null}
        {table && mapping ? (
          <>
            <div className="flex flex-wrap gap-2">
              <MappingSelect
                label="Title column"
                value={mapping.title}
                headers={table.headers}
                onChange={(title) => setMapping({ ...mapping, title })}
              />
              <MappingSelect
                label="Steps column"
                value={mapping.steps}
                headers={table.headers}
                onChange={(steps) => setMapping({ ...mapping, steps })}
              />
              <MappingSelect
                label="Expected column"
                value={mapping.expected}
                headers={table.headers}
                onChange={(expected) => setMapping({ ...mapping, expected })}
              />
              <MappingSelect
                label="Id column (optional)"
                value={mapping.id ?? ''}
                headers={table.headers}
                optional
                onChange={(id) => setMapping({ ...mapping, ...(id ? { id } : { id: undefined }) })}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="text-muted">
                    <th className="py-1 pr-2 font-medium">Title</th>
                    <th className="py-1 pr-2 font-medium">Expected</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} className="border-t border-border align-top">
                      <td className="py-1 pr-2">
                        <span className="font-mono text-muted">{row.id}</span> {row.title}
                      </td>
                      <td className="py-1 pr-2 text-text-2">{row.expected}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[12px] text-muted">
              Preview of the first 5 rows · {Math.min(table.records.length, MAX_SUITE_ROWS)} rows
              ready to import.
            </p>
          </>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={onImport} loading={importing} disabled={!canImport}>
            Import suite
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
