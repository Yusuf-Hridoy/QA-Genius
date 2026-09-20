'use client';

import { computeCoverage, uncoveredInstructions } from '@/lib/traceability/parse';
import { Card, CardHeader } from '@/components/ui/card';
import { MetricCard } from '@/components/ui/metric-card';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';

/**
 * Coverage metric for step 3: "AC covered n / total", uncovered ids as warn
 * pills, and a recovery button that refines with covering instructions.
 */
export function CoveragePanel({
  criteriaIds,
  cases,
  onGenerateUncovered,
}: {
  criteriaIds: string[];
  cases: Array<{ traceability: string }>;
  onGenerateUncovered: (instructions: string) => void;
}) {
  if (criteriaIds.length === 0) return null;
  const coverage = computeCoverage(criteriaIds, cases);
  const uncovered = coverage.uncoveredIds;

  return (
    <Card data-testid="coverage-panel">
      <CardHeader title="Traceability coverage" />
      <div className="flex flex-wrap items-center gap-2">
        <MetricCard label="AC covered" value={`${coverage.covered} / ${coverage.total}`} />
      </div>
      {uncovered.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] text-muted">Uncovered:</span>
          {uncovered.map((id) => (
            <Pill key={id} tone="warn">
              {id}
            </Pill>
          ))}
          <Button
            variant="ghost"
            onClick={() => onGenerateUncovered(uncoveredInstructions(uncovered))}
          >
            Generate cases for uncovered
          </Button>
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-muted">
          Every criterion is referenced by at least one case.
        </p>
      )}
    </Card>
  );
}
