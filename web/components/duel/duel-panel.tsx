'use client';

import { Fragment } from 'react';
import type { DuelFork, DuelResult } from '@/lib/duel/types';
import { findHighlights } from '@/lib/duel/highlights';
import { Card, CardHeader } from '@/components/ui/card';
import { Pill, type PillTone } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';

function severityTone(severity: string): PillTone {
  if (severity === 'high') return 'bad';
  if (severity === 'medium') return 'warn';
  return 'ok';
}

function agreementTone(ratio: number): PillTone {
  if (ratio >= 0.7) return 'ok';
  if (ratio >= 0.4) return 'warn';
  return 'bad';
}

function HighlightedStory({ story, forks }: { story: string; forks: DuelFork[] }) {
  // Recomputed live so marks always match the displayed story text.
  const ranges = findHighlights(
    story,
    forks.map((f) => ({ sourcePhrase: f.sourcePhrase })),
  );
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((h, i) => {
    if (h.start > cursor) parts.push(<span key={`t-${i}`}>{story.slice(cursor, h.start)}</span>);
    const fork = forks[h.forkIndex];
    const tipId = `duel-tip-${h.forkIndex}`;
    parts.push(
      <mark
        key={`m-${i}`}
        data-testid="duel-mark"
        tabIndex={0}
        aria-describedby={tipId}
        className="group relative cursor-help rounded-[3px] bg-hl-bg px-0.5 text-hl-fg"
      >
        {story.slice(h.start, h.end)}
        <span
          role="tooltip"
          id={tipId}
          className="absolute left-0 top-full z-10 hidden w-64 rounded-[var(--radius)] border border-border bg-card p-2 text-left text-[12px] font-normal text-text shadow-none group-hover:block group-focus:block"
        >
          <span className="font-medium">{fork?.topic ?? 'Fork'}</span>
          <span className="mt-1 block text-text-2">Strict: {fork?.readingA}</span>
          <span className="mt-1 block text-text-2">Permissive: {fork?.readingB}</span>
          <span className="mt-1 block">Rewrite: {fork?.suggestedRewrite}</span>
        </span>
      </mark>,
    );
    cursor = h.end;
  });
  if (cursor < story.length) parts.push(<span key="t-end">{story.slice(cursor)}</span>);
  return (
    <p className="text-[13px] leading-relaxed text-text" data-testid="duel-story">
      {parts}
    </p>
  );
}

function AlignedRows({
  aItems,
  bItems,
}: {
  aItems: Array<{ key: string; reading: string }>;
  bItems: Array<{ key: string; reading: string }>;
}) {
  const bByKey = new Map(bItems.map((b) => [b.key, b]));
  const keys = [
    ...aItems.map((a) => a.key),
    ...bItems.map((b) => b.key).filter((k) => !aItems.some((a) => a.key === k)),
  ];
  return (
    <div className="flex flex-col gap-2">
      {keys.map((key) => {
        const a = aItems.find((item) => item.key === key);
        const b = bByKey.get(key);
        const differs = (a?.reading ?? '') !== (b?.reading ?? '');
        return (
          <div
            key={key}
            className="grid gap-2 md:grid-cols-2"
            style={
              differs ? { borderLeft: '2px solid var(--accent)', paddingLeft: '8px' } : undefined
            }
            data-testid="duel-aligned-row"
          >
            <div>
              <p className="text-[12px] font-medium">
                {key} <span className="font-normal text-muted">· strict</span>
              </p>
              <p className="text-[13px] text-text-2">{a?.reading ?? 'Not addressed'}</p>
            </div>
            <div>
              <p className="text-[12px] font-medium">
                {key} <span className="font-normal text-muted">· permissive</span>
              </p>
              <p className="text-[13px] text-text-2">{b?.reading ?? 'Not addressed'}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Ambiguity Duel result: highlighted story, side-by-side readings, fork list
 * with apply-rewrite. Rendered above the INVEST card in step 1.
 */
export function DuelPanel({
  duel,
  storyText,
  onApplyRewrite,
}: {
  duel: DuelResult;
  storyText: string;
  /** Omitted on read-only surfaces (share page): rewrite buttons are hidden. */
  onApplyRewrite?: (sourcePhrase: string, suggestedRewrite: string) => void;
}) {
  const hasHigh = duel.forks.some((f) => f.severity === 'high');
  const percent = Math.round(duel.agreementRatio * 100);
  // Recomputed live so the count matches the displayed story text.
  const highlights = findHighlights(
    storyText,
    duel.forks.map((f) => ({ sourcePhrase: f.sourcePhrase })),
  );

  return (
    <Card data-testid="duel-panel">
      <CardHeader
        title="Ambiguity duel"
        actions={
          <div className="flex flex-wrap gap-1.5">
            <Pill tone={hasHigh ? 'bad' : 'warn'}>{duel.forks.length} forks</Pill>
            <Pill tone="warn">{highlights.length} vague phrases</Pill>
            <Pill tone={agreementTone(duel.agreementRatio)}>agreement {percent}%</Pill>
          </div>
        }
      />
      <div className="flex flex-col gap-4">
        <HighlightedStory story={storyText} forks={duel.forks} />

        <div className="grid gap-4">
          <div>
            <h3 className="mb-2 text-[13px] font-medium">Readings by topic</h3>
            <AlignedRows
              aItems={duel.a.rules.map((r) => ({ key: r.topic, reading: r.reading }))}
              bItems={duel.b.rules.map((r) => ({ key: r.topic, reading: r.reading }))}
            />
          </div>
          {(duel.a.numbers.length > 0 || duel.b.numbers.length > 0) && (
            <div>
              <h3 className="mb-2 text-[13px] font-medium">Numbers</h3>
              <AlignedRows
                aItems={duel.a.numbers.map((n) => ({ key: n.name, reading: n.value }))}
                bItems={duel.b.numbers.map((n) => ({ key: n.name, reading: n.value }))}
              />
            </div>
          )}
        </div>

        <div>
          <h3 className="mb-2 text-[13px] font-medium">Forks</h3>
          <ul className="flex flex-col gap-2">
            {duel.forks.map((fork, i) => (
              <li
                key={i}
                className="rounded-[var(--radius)] border border-border bg-card-2 p-2.5"
                data-testid="duel-fork"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-medium">{fork.topic}</span>
                  <Pill tone={severityTone(fork.severity)}>{fork.severity}</Pill>
                </div>
                <p className="mt-1 text-[13px] text-text-2">
                  <span className="font-medium text-text">Strict: </span>
                  {fork.readingA}
                </p>
                <p className="mt-1 text-[13px] text-text-2">
                  <span className="font-medium text-text">Permissive: </span>
                  {fork.readingB}
                </p>
                <p className="mt-1 text-[13px]">
                  <span className="font-medium">Rewrite: </span>
                  {fork.suggestedRewrite}
                </p>
                {onApplyRewrite ? (
                  <div className="mt-1.5">
                    <Button
                      variant="ghost"
                      onClick={() => onApplyRewrite(fork.sourcePhrase, fork.suggestedRewrite)}
                    >
                      Apply rewrite
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {duel.agreements.length > 0 && (
            <Fragment>
              <h3 className="mb-1 mt-3 text-[13px] font-medium">Agreements</h3>
              <ul className="list-disc pl-5 text-[13px] text-text-2">
                {duel.agreements.map((agreement, i) => (
                  <li key={i}>{agreement}</li>
                ))}
              </ul>
            </Fragment>
          )}
        </div>
      </div>
    </Card>
  );
}
