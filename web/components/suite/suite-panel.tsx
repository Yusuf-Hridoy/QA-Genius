'use client';

import { Upload } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/card';
import { MetricCard } from '@/components/ui/metric-card';
import { Button } from '@/components/ui/button';

/**
 * Existing-suite coverage: "{covered} covered · {gap} new" metric, re-import,
 * and gaps-only CSV/XLSX export. The model is never consulted for matching.
 */
export function SuitePanel({
  fileName,
  rowCount,
  covered,
  gap,
  total,
  onUpload,
  onExportGapsCsv,
  onExportGapsXlsx,
}: {
  fileName?: string;
  rowCount?: number;
  covered: number;
  gap: number;
  total: number;
  onUpload: () => void;
  onExportGapsCsv: () => void;
  onExportGapsXlsx: () => void;
}) {
  if (!fileName) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onUpload}>
          <Upload className="h-3.5 w-3.5" aria-hidden />
          Compare with your suite
        </Button>
      </div>
    );
  }
  return (
    <Card data-testid="suite-panel">
      <CardHeader title="Existing suite" />
      <div className="flex flex-wrap items-center gap-2">
        <MetricCard label="Covered" value={covered} />
        <MetricCard label="New" value={gap} />
        <p className="text-[12px] text-muted">
          {fileName} · {rowCount ?? 0} rows · {total} generated
        </p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onUpload}>
          <Upload className="h-3.5 w-3.5" aria-hidden />
          Re-import suite
        </Button>
        <Button variant="secondary" onClick={onExportGapsCsv} disabled={gap === 0}>
          Export gaps CSV
        </Button>
        <Button variant="secondary" onClick={onExportGapsXlsx} disabled={gap === 0}>
          Export gaps XLSX
        </Button>
      </div>
    </Card>
  );
}
