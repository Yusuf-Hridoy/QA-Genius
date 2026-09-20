'use client';

import { Copy } from 'lucide-react';
import type { VaguePhrase } from '@/lib/generators/story-analyzer/schema';
import { Card, CardHeader } from '@/components/ui/card';
import { Pill, type PillTone } from '@/components/ui/pill';
import { Skeleton } from '@/components/ui/skeleton';
import { copyWithToast } from '@/components/ui/copy-button';
import { Button } from '@/components/ui/button';
import { GherkinBlock } from './gherkin-block';
import { arr, num, str } from './partial-data';
import type { ResultProps } from './types';

const INVEST_FIELDS = [
  ['invest_independent', 'Independent'],
  ['invest_negotiable', 'Negotiable'],
  ['invest_valuable', 'Valuable'],
  ['invest_estimable', 'Estimable'],
  ['invest_small', 'Small'],
  ['invest_testable', 'Testable'],
] as const;

function investTone(value: string): PillTone {
  const v = value.trim().toUpperCase();
  if (v.startsWith('PASS')) return 'ok';
  if (v.startsWith('PARTIAL')) return 'warn';
  if (v.startsWith('FAIL')) return 'bad';
  return 'neutral';
}

function severityTone(severity: string): PillTone {
  const v = severity.trim().toLowerCase();
  if (v === 'high') return 'bad';
  if (v === 'medium') return 'warn';
  if (v === 'low') return 'ok';
  return 'neutral';
}

function scoreTone(score: number): PillTone {
  if (score <= 30) return 'ok';
  if (score <= 60) return 'warn';
  return 'bad';
}

function StorySkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-5 w-40 rounded-full" />
      </div>
      <Skeleton className="h-40 w-full rounded-[var(--radius-card)]" />
      <Skeleton className="h-32 w-full rounded-[var(--radius-card)]" />
      <Skeleton className="h-48 w-full rounded-[var(--radius-card)]" />
    </div>
  );
}

export function StoryResult({ data, isLoading }: ResultProps) {
  if (!data) {
    return isLoading ? <StorySkeleton /> : null;
  }

  const score = num(data.ambiguity_score);
  const investOverall = str(data.invest_overall);
  const vaguePhrases = arr<VaguePhrase>(data.vague_phrases);
  const missing = arr<string>(data.missing_elements);
  const risks = arr<string>(data.risks);
  const rewrites = arr<string>(data.suggested_rewrites);
  const acceptance = arr<string>(data.generated_acceptance_criteria);
  const recommendedSplit = arr<string>(data.recommended_split);
  const scoreBreakdown = str(data.score_breakdown);

  return (
    <div className="flex flex-col gap-3" data-testid="story-result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-[15px] font-semibold">Story analysis</h2>
        {score !== undefined ? (
          <Pill tone={scoreTone(score)}>
            Ambiguity {score}/100 · {str(data.clarity_label) || '…'}
          </Pill>
        ) : (
          <Skeleton className="h-5 w-40 rounded-full" />
        )}
      </div>

      <Card>
        <CardHeader
          title="INVEST"
          actions={
            investOverall ? (
              <Pill tone={investTone(investOverall)}>Overall: {investOverall}</Pill>
            ) : undefined
          }
        />
        <table className="w-full text-left">
          <tbody>
            {INVEST_FIELDS.map(([field, label]) => {
              const value = str(data[field]);
              return (
                <tr key={field} className="border-t border-border first:border-0">
                  <th scope="row" className="w-32 py-2 pr-3 align-top text-[13px] font-medium">
                    {label}
                  </th>
                  <td className="py-2 text-[13px] text-text-2">
                    {value ? (
                      <>
                        <Pill tone={investTone(value)}>{value.split('  --  ')[0]}</Pill>
                        {value.includes('  --  ') ? (
                          <span className="ml-2">{value.split('  --  ')[1]}</span>
                        ) : null}
                      </>
                    ) : isLoading ? (
                      <Skeleton className="h-4 w-24" />
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card>
        <CardHeader title="Vague phrases" />
        {vaguePhrases.length === 0 && isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <ul className="flex flex-col gap-3">
            {vaguePhrases.map((vp, i) => (
              <li key={i} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded-[var(--radius)] bg-hl-bg px-1.5 py-0.5 font-mono text-[12px] text-hl-fg">
                    {vp.phrase}
                  </code>
                  <Pill tone={severityTone(vp.severity)}>{vp.severity}</Pill>
                </div>
                <p className="text-[13px] text-text-2">{vp.suggestion}</p>
                <p className="text-[13px]">
                  <span className="font-medium">Replacement: </span>
                  {vp.replacement}
                </p>
              </li>
            ))}
          </ul>
        )}
        {vaguePhrases.length === 0 && !isLoading ? (
          <p className="text-[13px] text-muted">No vague phrases found.</p>
        ) : null}
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader title="Missing elements" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {missing.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
          {missing.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
        </Card>
        <Card>
          <CardHeader title="Risks" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {risks.map((risk, i) => (
              <li key={i}>{risk}</li>
            ))}
          </ul>
          {risks.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
        </Card>
      </div>

      <Card>
        <CardHeader title="Suggested rewrites" />
        <ol className="flex flex-col gap-2">
          {rewrites.map((rewrite, i) => (
            <li key={i} className="flex items-start justify-between gap-2">
              <span className="text-[13px]">
                {i + 1}. {rewrite}
              </span>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Copy rewrite"
                onClick={() => void copyWithToast(rewrite, 'Rewrite copied')}
              >
                <Copy className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </li>
          ))}
        </ol>
        {rewrites.length === 0 && isLoading ? <Skeleton className="h-16 w-full" /> : null}
      </Card>

      <Card>
        <CardHeader title="Acceptance criteria" />
        <div className="flex flex-col gap-2">
          {acceptance.map((ac, i) => (
            <GherkinBlock key={i} code={ac} title={`acceptance-criteria-${i + 1}.feature`} />
          ))}
          {acceptance.length === 0 && isLoading ? <Skeleton className="h-32 w-full" /> : null}
        </div>
      </Card>

      {recommendedSplit.length > 0 ? (
        <Card>
          <CardHeader title="Recommended split" />
          <ul className="list-disc pl-5 text-[13px] text-text-2">
            {recommendedSplit.map((story, i) => (
              <li key={i}>{story}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      {scoreBreakdown ? (
        <details className="rounded-[var(--radius-card)] border border-border bg-card px-4 py-3">
          <summary className="cursor-pointer text-[13px] font-medium">
            How the score was computed
          </summary>
          <pre className="mt-2 overflow-x-auto font-mono text-[12px] text-text-2">
            {scoreBreakdown}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
