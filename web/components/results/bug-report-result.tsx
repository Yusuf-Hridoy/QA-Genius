'use client';

import { Card, CardHeader } from '@/components/ui/card';
import { Pill, type PillTone } from '@/components/ui/pill';
import { Skeleton } from '@/components/ui/skeleton';
import { arr, str } from './partial-data';
import type { ResultProps } from './types';

function severityTone(severity: string): PillTone {
  switch (severity.trim().toLowerCase()) {
    case 'critical':
    case 'high':
      return 'bad';
    case 'medium':
      return 'warn';
    case 'low':
      return 'ok';
    default:
      return 'neutral';
  }
}

function regressionTone(risk: string): PillTone {
  if (risk.startsWith('High')) return 'bad';
  if (risk.startsWith('Medium')) return 'warn';
  if (risk.startsWith('Low')) return 'ok';
  return 'neutral';
}

function BugSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-40 w-full rounded-[var(--qg-radius-card)]" />
      <Skeleton className="h-32 w-full rounded-[var(--qg-radius-card)]" />
    </div>
  );
}

export function BugReportResult({ data, isLoading }: ResultProps) {
  if (!data) {
    return isLoading ? <BugSkeleton /> : null;
  }

  const title = str(data.title);
  const severity = str(data.severity);
  const reproducibility = str(data.reproducibility_rate);
  const rootCause = str(data.root_cause_category);
  const regressionRisk = str(data.regression_risk);
  const environment = str(data.environment_details);
  const steps = arr<string>(data.steps_to_reproduce);
  const actual = str(data.actual_result);
  const expected = str(data.expected_result);

  const relatedAreas = arr<string>(data.related_areas);
  const jiraLabels = arr<string>(data.jira_labels);
  const investigationSteps = arr<string>(data.investigation_steps);
  const relatedIssues = arr<string>(data.related_issues);
  const annotations = arr<string>(data.screenshot_annotations);

  const optionalBlocks: { heading: string; content: React.ReactNode }[] = [
    {
      heading: 'Suspected pattern',
      content: str(data.suspected_pattern) || null,
    },
    {
      heading: 'Suggested fix',
      content: str(data.suggested_fix) || null,
    },
    {
      heading: 'Workaround',
      content: str(data.workaround) || null,
    },
    {
      heading: 'Business impact',
      content: str(data.business_impact) || null,
    },
    {
      heading: 'Affected users',
      content: str(data.affected_users) || null,
    },
  ].filter((block) => block.content !== null);

  return (
    <div className="flex flex-col gap-3" data-testid="bug-report-result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="min-w-0 flex-1 font-display text-[15px] font-semibold">
          {title || (isLoading ? '…' : 'Bug report')}
        </h2>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {severity ? <Pill tone={severityTone(severity)}>Severity: {severity}</Pill> : null}
        {reproducibility ? <Pill tone="neutral">{reproducibility}</Pill> : null}
        {rootCause ? <Pill tone="neutral">{rootCause}</Pill> : null}
        {regressionRisk ? (
          <Pill tone={regressionTone(regressionRisk)}>Regression risk: {regressionRisk}</Pill>
        ) : null}
        {severity === '' && isLoading ? <Skeleton className="h-5 w-40 rounded-full" /> : null}
      </div>

      {environment ? (
        <pre className="overflow-x-auto rounded-[var(--qg-radius)] border border-border bg-card-2 p-3 font-mono text-[12px] text-text-2">
          {environment}
        </pre>
      ) : null}

      <Card>
        <CardHeader title="Steps to reproduce" />
        <ol className="list-decimal pl-5 text-[13px] text-text-2">
          {steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
        {steps.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader title="Actual result" />
          <p className="text-[13px] text-text-2">{actual || (isLoading ? '…' : '')}</p>
        </Card>
        <Card>
          <CardHeader title="Expected result" />
          <p className="text-[13px] text-text-2">{expected || (isLoading ? '…' : '')}</p>
        </Card>
      </div>

      {optionalBlocks.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {optionalBlocks.map((block) => (
            <Card key={block.heading}>
              <CardHeader title={block.heading} />
              <p className="text-[13px] text-text-2">{block.content}</p>
            </Card>
          ))}
        </div>
      ) : null}

      {relatedAreas.length > 0 ? (
        <Card>
          <CardHeader title="Related areas" />
          <div className="flex flex-wrap gap-1">
            {relatedAreas.map((area) => (
              <Pill key={area} tone="neutral">
                {area}
              </Pill>
            ))}
          </div>
        </Card>
      ) : null}

      {jiraLabels.length > 0 ? (
        <Card>
          <CardHeader title="Jira labels" />
          <div className="flex flex-wrap gap-1">
            {jiraLabels.map((label) => (
              <Pill key={label} tone="accent">
                {label}
              </Pill>
            ))}
          </div>
        </Card>
      ) : null}

      {investigationSteps.length > 0 ? (
        <Card>
          <CardHeader title="Investigation steps" />
          <ul className="flex flex-col gap-1.5">
            {investigationSteps.map((step, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] text-text-2">
                <input
                  type="checkbox"
                  disabled
                  aria-label={`Investigation step ${i + 1}`}
                  className="mt-0.5 h-4 w-4 accent-[var(--qg-accent)]"
                />
                {step}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {relatedIssues.length > 0 ? (
        <Card>
          <CardHeader title="Related issues" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {relatedIssues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      {annotations.length > 0 ? (
        <Card>
          <CardHeader title="Screenshot annotations" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {annotations.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
