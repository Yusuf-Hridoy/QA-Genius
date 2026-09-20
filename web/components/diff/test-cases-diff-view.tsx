'use client';

import { useState } from 'react';
import type { TestCasesDiff } from '@/lib/diff/test-cases';
import { Card, CardHeader } from '@/components/ui/card';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';
import { WordDiff } from './word-diff';

/**
 * Revision diff for test cases: summary pills, changes-only filter, cards
 * with a status left border, inline word diffs. Accept writes the revision
 * to the run (old output goes to history); Keep discards it.
 */
export function TestCasesDiffView({
  diff,
  canUndo,
  onAccept,
  onKeep,
  onUndo,
}: {
  diff: TestCasesDiff;
  canUndo: boolean;
  onAccept: () => void;
  onKeep: () => void;
  onUndo: () => void;
}) {
  const [changesOnly, setChangesOnly] = useState(false);
  const visible = changesOnly ? diff.cases.filter((c) => c.status !== 'unchanged') : diff.cases;

  return (
    <Card data-testid="test-cases-diff">
      <CardHeader
        title="Revision diff"
        actions={
          <div className="flex flex-wrap gap-1.5">
            <Pill tone="ok">+{diff.added} added</Pill>
            <Pill tone="warn">~{diff.changed} changed</Pill>
            <Pill tone="bad">−{diff.removed} removed</Pill>
            <Pill tone="neutral">{diff.unchanged} unchanged</Pill>
          </div>
        }
      />
      <div className="flex flex-col gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-text-2">
          <input
            type="checkbox"
            checked={changesOnly}
            onChange={(e) => setChangesOnly(e.target.checked)}
            className="h-4 w-4 accent-[var(--accent)]"
          />
          Show only changes
        </label>
        {visible.map((entry) => (
          <div
            key={`${entry.status}-${entry.id}`}
            data-testid={`diff-${entry.status}`}
            className="rounded-[var(--radius)] border border-border bg-card-2 p-2.5"
            style={
              entry.status === 'added'
                ? { borderLeft: '3px solid var(--ok-fg)' }
                : entry.status === 'changed'
                  ? { borderLeft: '3px solid var(--warn-fg)' }
                  : entry.status === 'removed'
                    ? { borderLeft: '3px solid var(--bad-fg)' }
                    : undefined
            }
          >
            <p className="font-mono text-[12px] text-muted">
              {entry.id} · {entry.status}
              {entry.changedFields && entry.changedFields.length > 0
                ? ` · ${entry.changedFields.join(', ')}`
                : ''}
            </p>
            {entry.status === 'added' && entry.revised ? (
              <p className="mt-1 text-[13px] font-medium">{entry.revised.title}</p>
            ) : null}
            {entry.status === 'removed' && entry.current ? (
              <p className="mt-1 text-[13px] text-text-2 line-through">{entry.current.title}</p>
            ) : null}
            {entry.status === 'changed' && entry.current && entry.revised ? (
              <div className="mt-1 flex flex-col gap-1 text-[13px]">
                {entry.changedFields?.includes('title') && entry.titleDiff ? (
                  <p>
                    <span className="font-medium">Title: </span>
                    <WordDiff parts={entry.titleDiff} />
                  </p>
                ) : (
                  <p className="font-medium">{entry.revised.title}</p>
                )}
                {(entry.changedFields ?? []).filter((f) => f === 'priority' || f === 'category')
                  .length > 0 ? (
                  <p className="text-text-2">
                    {entry.current.priority} → {entry.revised.priority} · {entry.current.category} →{' '}
                    {entry.revised.category}
                  </p>
                ) : null}
                {entry.changedFields?.includes('expected') && entry.expectedDiff ? (
                  <p>
                    <span className="font-medium">Expected: </span>
                    <WordDiff parts={entry.expectedDiff} />
                  </p>
                ) : null}
                {entry.changedFields?.includes('steps') && entry.stepsOps ? (
                  <ol className="list-decimal pl-5">
                    {entry.stepsOps.map((op, i) => (
                      <li
                        key={i}
                        className={
                          op.op === 'added'
                            ? 'rounded-[3px] bg-ok-bg underline decoration-ok-fg underline-offset-2'
                            : op.op === 'removed'
                              ? 'rounded-[3px] bg-bad-bg line-through decoration-bad-fg'
                              : undefined
                        }
                      >
                        {op.text}
                      </li>
                    ))}
                  </ol>
                ) : null}
              </div>
            ) : null}
            {entry.status === 'unchanged' && entry.current ? (
              <p className="mt-1 text-[13px] text-text-2">{entry.current.title}</p>
            ) : null}
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={onAccept}>
            Accept revision
          </Button>
          <Button variant="secondary" onClick={onKeep}>
            Keep current
          </Button>
          {canUndo ? (
            <Button variant="ghost" onClick={onUndo}>
              Undo last accept
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
