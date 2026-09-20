'use client';

import { useMemo, useState } from 'react';
import type { TestCase } from '@/lib/generators/test-cases/schema';
import { parseTraceabilityRefs } from '@/lib/traceability/parse';
import type { SuiteMatch } from '@/lib/suite/match';
import { Card, CardHeader } from '@/components/ui/card';
import { GherkinBlock } from './gherkin-block';
import { MetricCard } from '@/components/ui/metric-card';
import { Pill, type PillTone } from '@/components/ui/pill';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils/cn';
import { arr, num, record, str } from './partial-data';
import type { ResultProps } from './types';

const CATEGORY_ORDER = ['Functional', 'Boundary', 'Edge Case', 'Negative'];
const PRIORITY_ORDER = ['High', 'Medium', 'Low'];

function categoryTone(category: string): PillTone {
  switch (category) {
    case 'Functional':
      return 'info';
    case 'Negative':
      return 'warn';
    case 'Boundary':
      return 'accent';
    default:
      return 'neutral';
  }
}

function priorityTone(priority: string): PillTone {
  switch (priority) {
    case 'High':
      return 'bad';
    case 'Medium':
      return 'warn';
    case 'Low':
      return 'ok';
    default:
      return 'neutral';
  }
}

function feasibilityTone(feasibility: string): PillTone {
  switch (feasibility) {
    case 'High':
      return 'ok';
    case 'Medium':
      return 'warn';
    case 'Low':
      return 'bad';
    default:
      return 'neutral';
  }
}

function effortTone(effort: string): PillTone {
  const e = effort.trim().toLowerCase();
  if (e === 'low' || e === 'quick') return 'ok';
  if (e === 'moderate') return 'warn';
  if (e === 'high' || e === 'complex') return 'bad';
  return 'neutral';
}

function categoryRank(category: string): number {
  const i = CATEGORY_ORDER.indexOf(category);
  return i === -1 ? CATEGORY_ORDER.length : i;
}

function priorityRank(priority: string): number {
  const i = PRIORITY_ORDER.indexOf(priority);
  return i === -1 ? PRIORITY_ORDER.length : i;
}

function sortCases(cases: TestCase[]): TestCase[] {
  return [...cases].sort(
    (a, b) =>
      categoryRank(a.category) - categoryRank(b.category) ||
      priorityRank(a.priority) - priorityRank(b.priority) ||
      a.id.localeCompare(b.id),
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors duration-[var(--dur)]',
        active
          ? 'border-accent bg-accent-soft text-accent'
          : 'border-border-strong bg-card text-text-2 hover:bg-card-2',
      )}
    >
      {label}
    </button>
  );
}

export type TestCaseSelection = {
  selected: string[];
  onToggle: (id: string) => void;
};

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** Deterministic traceability chips: parsed AC-n ids, else the raw text. */
function TraceChips({
  traceability,
  onCriterionClick,
}: {
  traceability: string;
  onCriterionClick?: (id: string) => void;
}) {
  const refs = parseTraceabilityRefs(traceability ?? '');
  const rest = (traceability ?? '')
    .replace(/AC-\d+/gi, '')
    .replace(/^[,\s;]+|[,\s;]+$/g, '')
    .trim();
  if (refs.length === 0 && !rest) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1" data-testid="trace-chips">
      {refs.map((id) =>
        onCriterionClick ? (
          <button
            key={id}
            type="button"
            onClick={() => onCriterionClick(id)}
            aria-label={`Show ${id} in acceptance criteria`}
            className="rounded-full"
          >
            <Pill tone="accent">{id}</Pill>
          </button>
        ) : (
          <Pill key={id} tone="accent">
            {id}
          </Pill>
        ),
      )}
      {rest ? <Pill tone="neutral">{truncate(rest, 24)}</Pill> : null}
    </div>
  );
}

function SuiteChip({ match }: { match: SuiteMatch }) {
  if (match.status === 'gap') {
    return (
      <span data-testid="suite-chip">
        <Pill tone="bad">gap · not in your suite</Pill>
      </span>
    );
  }
  return (
    <span title={`${match.title} · score ${match.score.toFixed(2)}`} data-testid="suite-chip">
      <Pill tone={match.status === 'covered' ? 'neutral' : 'warn'}>
        {match.status} · {match.suiteId}
      </Pill>
    </span>
  );
}

function TestCaseCard({
  testCase,
  selection,
  match,
  onCriterionClick,
}: {
  testCase: TestCase;
  selection?: TestCaseSelection;
  match?: SuiteMatch;
  onCriterionClick?: (id: string) => void;
}) {
  const tags = arr<string>(testCase.tags);
  const steps = arr<string>(testCase.steps);
  const checked = selection?.selected.includes(testCase.id) ?? false;
  return (
    <Card data-testid="test-case-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="min-w-0 flex-1 text-[14px] font-medium">
          {selection ? (
            <input
              type="checkbox"
              checked={checked}
              onChange={() => selection.onToggle(testCase.id)}
              aria-label={`Select ${testCase.id}`}
              className="mr-2 h-4 w-4 align-middle accent-[var(--accent)]"
            />
          ) : null}
          <span className="mr-2 font-mono text-[12px] text-muted">{testCase.id}</span>
          {testCase.title}
        </h3>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Pill tone={categoryTone(testCase.category)}>{testCase.category}</Pill>
        <Pill tone={priorityTone(testCase.priority)}>{testCase.priority} priority</Pill>
        <Pill tone={feasibilityTone(testCase.automation_feasibility)}>
          Feasibility: {testCase.automation_feasibility}
        </Pill>
        <Pill tone={effortTone(testCase.automation_effort)}>
          Effort: {testCase.automation_effort}
        </Pill>
      </div>
      {testCase.pre_conditions ? (
        <p className="mt-2 text-[13px] text-text-2">
          <span className="font-medium text-text">Pre-conditions: </span>
          {testCase.pre_conditions}
        </p>
      ) : null}
      {steps.length > 0 ? (
        <ol className="mt-2 list-decimal pl-5 text-[13px] text-text-2">
          {steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      ) : null}
      <p className="mt-2 text-[13px]">
        <span className="font-medium">Expected result: </span>
        {testCase.expected_result}
      </p>
      {testCase.test_data ? (
        <pre className="mt-2 overflow-x-auto rounded-[var(--radius)] bg-card-2 p-2 font-mono text-[12px] text-text-2">
          {testCase.test_data}
        </pre>
      ) : null}
      {testCase.bdd_scenario ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[12px] font-medium text-text-2">
            BDD scenario
          </summary>
          <div className="mt-1.5">
            <GherkinBlock code={testCase.bdd_scenario} />
          </div>
        </details>
      ) : null}
      {tags.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {tags.map((tag) => (
            <Pill key={tag} tone="neutral">
              {tag}
            </Pill>
          ))}
        </div>
      ) : null}
      {testCase.traceability ? (
        <p className="mt-2 font-mono text-[12px] text-muted">
          Validates: “{testCase.traceability}”
        </p>
      ) : null}
      <TraceChips traceability={testCase.traceability} onCriterionClick={onCriterionClick} />
      {match ? (
        <div className="mt-2 flex flex-wrap gap-1">
          <SuiteChip match={match} />
        </div>
      ) : null}
    </Card>
  );
}

function TestCasesSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-56 w-full rounded-[var(--radius-card)]" />
      <Skeleton className="h-56 w-full rounded-[var(--radius-card)]" />
    </div>
  );
}

export function TestCasesResult({
  data,
  isLoading,
  selection,
  suiteMatches,
  gapsOnly,
  onGapsOnlyChange,
  onCriterionClick,
}: ResultProps & {
  selection?: TestCaseSelection;
  /** Existing-suite matches by test case id; enables the match chip + gaps filter. */
  suiteMatches?: Record<string, SuiteMatch>;
  gapsOnly?: boolean;
  onGapsOnlyChange?: (gapsOnly: boolean) => void;
  onCriterionClick?: (id: string) => void;
}) {
  const [categoryFilter, setCategoryFilter] = useState<string[]>([]);
  const [priorityFilter, setPriorityFilter] = useState<string[]>([]);
  const [feasibilityFilter, setFeasibilityFilter] = useState<string[]>([]);

  const summary = record(data?.summary);
  const cases = useMemo<TestCase[]>(
    () =>
      arr<Record<keyof TestCase, unknown> & Record<string, unknown>>(data?.test_cases).map(
        (raw) => ({
          ...(raw as unknown as TestCase),
          tags: arr<string>(raw.tags),
          steps: arr<string>(raw.steps),
        }),
      ),
    [data?.test_cases],
  );

  if (!data) {
    return isLoading ? <TestCasesSkeleton /> : null;
  }

  const total = num(summary.total_generated);
  const categoryBreakdown = arr<{ category: string; count: number }>(summary.category_breakdown);
  const coverageGaps = arr<string>(summary.coverage_gaps);
  const recommendations = arr<string>(summary.recommendations);
  const automationPotential = str(summary.automation_coverage_potential);

  const categoriesPresent = CATEGORY_ORDER.filter((c) => cases.some((tc) => tc.category === c));
  const hasFilters =
    categoryFilter.length + priorityFilter.length + feasibilityFilter.length > 0 ||
    gapsOnly === true;

  const filtered = cases.filter(
    (tc) =>
      (categoryFilter.length === 0 || categoryFilter.includes(tc.category)) &&
      (priorityFilter.length === 0 || priorityFilter.includes(tc.priority)) &&
      (feasibilityFilter.length === 0 || feasibilityFilter.includes(tc.automation_feasibility)) &&
      (gapsOnly !== true || suiteMatches?.[tc.id]?.status === 'gap'),
  );
  const sorted = sortCases(filtered);

  const toggle = (list: string[], setList: (v: string[]) => void, value: string) => {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };
  const clearFilters = () => {
    setCategoryFilter([]);
    setPriorityFilter([]);
    setFeasibilityFilter([]);
    onGapsOnlyChange?.(false);
  };

  return (
    <div className="flex flex-col gap-3" data-testid="test-cases-result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-[15px] font-semibold">Test cases</h2>
        {total !== undefined ? (
          <Pill tone="accent">
            {sorted.length} of {cases.length} shown
          </Pill>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
        <MetricCard label="Total" value={total ?? '…'} />
        {categoryBreakdown.map((c) => (
          <MetricCard key={c.category} label={c.category} value={c.count} />
        ))}
        <MetricCard
          label="Automation potential"
          value={automationPotential ? automationPotential.split('  --  ')[0] : '…'}
          sub={
            automationPotential.includes('  --  ')
              ? automationPotential.split('  --  ')[1]
              : undefined
          }
          className="col-span-2"
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5 rounded-[var(--radius-card)] border border-border bg-card p-2.5">
        <span className="mr-1 text-[11px] font-medium uppercase tracking-wide text-muted">
          Category
        </span>
        {categoriesPresent.map((category) => (
          <FilterChip
            key={category}
            label={category}
            active={categoryFilter.includes(category)}
            onClick={() => toggle(categoryFilter, setCategoryFilter, category)}
          />
        ))}
        <span className="mx-1 text-[11px] font-medium uppercase tracking-wide text-muted">
          Priority
        </span>
        {PRIORITY_ORDER.map((priority) => (
          <FilterChip
            key={priority}
            label={priority}
            active={priorityFilter.includes(priority)}
            onClick={() => toggle(priorityFilter, setPriorityFilter, priority)}
          />
        ))}
        <span className="mx-1 text-[11px] font-medium uppercase tracking-wide text-muted">
          Feasibility
        </span>
        {['High', 'Medium', 'Low'].map((feasibility) => (
          <FilterChip
            key={feasibility}
            label={feasibility}
            active={feasibilityFilter.includes(feasibility)}
            onClick={() => toggle(feasibilityFilter, setFeasibilityFilter, feasibility)}
          />
        ))}
        {suiteMatches ? (
          <FilterChip
            label="Gaps only"
            active={gapsOnly === true}
            onClick={() => onGapsOnlyChange?.(!(gapsOnly === true))}
          />
        ) : null}
        {hasFilters ? (
          <button
            type="button"
            onClick={clearFilters}
            className="ml-auto text-[11px] font-medium text-accent hover:underline"
          >
            Clear
          </button>
        ) : null}
      </div>

      <div className="flex flex-col gap-3">
        {sorted.map((tc) => (
          <TestCaseCard
            key={tc.id}
            testCase={tc}
            selection={selection}
            match={suiteMatches?.[tc.id]}
            onCriterionClick={onCriterionClick}
          />
        ))}
        {cases.length === 0 && isLoading ? (
          <>
            <Skeleton className="h-56 w-full rounded-[var(--radius-card)]" />
            <Skeleton className="h-56 w-full rounded-[var(--radius-card)]" />
          </>
        ) : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader title="Coverage gaps" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {coverageGaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
          {coverageGaps.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
        </Card>
        <Card>
          <CardHeader title="Recommendations" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {recommendations.map((rec, i) => (
              <li key={i}>{rec}</li>
            ))}
          </ul>
          {recommendations.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
        </Card>
      </div>
    </div>
  );
}
