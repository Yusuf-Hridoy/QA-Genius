'use client';

import type { StoryDiff } from '@/lib/diff/story';
import { Card, CardHeader } from '@/components/ui/card';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';
import { WordDiff } from './word-diff';

function fieldLabel(field: string): string {
  return field
    .replace('invest_', '')
    .replace(/_/g, ' ')
    .replace(/^\w/, (c) => c.toUpperCase());
}

/** Field-level diff for a story revision: scalars, sets, criteria word diffs. */
export function StoryDiffView({
  diff,
  onAccept,
  onKeep,
}: {
  diff: StoryDiff;
  onAccept: () => void;
  onKeep: () => void;
}) {
  const changedScalars = diff.scalars.filter((s) => s.changed);
  const changedArrays = diff.arrays.filter((a) => a.added.length > 0 || a.removed.length > 0);
  const changedCriteria = diff.criteria.kept.filter((k) => k.changed);

  return (
    <Card data-testid="story-diff">
      <CardHeader
        title="Revision diff"
        actions={diff.changed ? <Pill tone="warn">changed</Pill> : <Pill tone="ok">unchanged</Pill>}
      />
      <div className="flex flex-col gap-3 text-[13px]">
        {changedScalars.length > 0 && (
          <div>
            <h3 className="mb-1 font-medium">Scores and INVEST</h3>
            <ul className="flex flex-col gap-1">
              {changedScalars.map((s) => (
                <li key={s.field} className="text-text-2">
                  {fieldLabel(s.field)}: {s.before || '—'} → {s.after || '—'}
                </li>
              ))}
            </ul>
          </div>
        )}
        {changedArrays.map((a) => (
          <div key={a.field}>
            <h3 className="mb-1 font-medium">{fieldLabel(a.field)}</h3>
            {a.added.map((line, i) => (
              <p key={`a-${i}`} className="rounded-[3px] bg-ok-bg px-1 text-text-2">
                + {line}
              </p>
            ))}
            {a.removed.map((line, i) => (
              <p key={`r-${i}`} className="rounded-[3px] bg-bad-bg px-1 text-text-2 line-through">
                − {line}
              </p>
            ))}
          </div>
        ))}
        {(changedCriteria.length > 0 ||
          diff.criteria.added.length > 0 ||
          diff.criteria.removed.length > 0) && (
          <div>
            <h3 className="mb-1 font-medium">Acceptance criteria</h3>
            {changedCriteria.map((k) => (
              <p key={k.index} className="text-text-2">
                <WordDiff parts={k.diff} />
              </p>
            ))}
            {diff.criteria.added.map((line, i) => (
              <p key={`a-${i}`} className="rounded-[3px] bg-ok-bg px-1 text-text-2">
                + {line}
              </p>
            ))}
            {diff.criteria.removed.map((line, i) => (
              <p key={`r-${i}`} className="rounded-[3px] bg-bad-bg px-1 text-text-2 line-through">
                − {line}
              </p>
            ))}
          </div>
        )}
        {!diff.changed && <p className="text-muted">The revision matches the current output.</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={onAccept}>
            Accept revision
          </Button>
          <Button variant="secondary" onClick={onKeep}>
            Keep current
          </Button>
        </div>
      </div>
    </Card>
  );
}
