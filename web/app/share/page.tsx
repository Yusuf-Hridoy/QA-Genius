'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { Run } from '@/lib/pipeline/types';
import { activeStep } from '@/lib/pipeline/steps';
import { ShareDecodeError, decodeShare } from '@/lib/share/codec';
import {
  parseSharedRun,
  sharedCriteria,
  sharedDuel,
  sharedStoryInput,
  sharedStoryOutput,
  sharedTestCases,
} from '@/lib/share/shared-run';
import { RunStepper } from '@/components/requirements/run-stepper';
import { StoryResult, TestCasesResult } from '@/components/results';
import { StoryExports, TestCasesExports } from '@/components/results/export-buttons';
import { DuelPanel } from '@/components/duel/duel-panel';
import { Card, CardHeader } from '@/components/ui/card';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { FileText } from 'lucide-react';
import { useRunStore } from '@/lib/store/run';
import { getSuite } from '@/lib/suite/db';
import { matchSuite, type SuiteMatch } from '@/lib/suite/match';
import { projectSlug } from '@/lib/exports/download';

type ShareState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; run: Run; projectName: string };

function toRecord(value: unknown): Record<string, unknown> {
  return value as unknown as Record<string, unknown>;
}

/** Public read-only page. The payload lives in the URL fragment (never sent to the server). */
export default function SharePage() {
  const router = useRouter();
  const adoptSharedRun = useRunStore((s) => s.adoptSharedRun);
  const [state, setState] = useState<ShareState>({ status: 'loading' });
  const [suiteMatches, setSuiteMatches] = useState<Record<string, SuiteMatch> | undefined>(
    undefined,
  );
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    try {
      const fragment = window.location.hash.startsWith('#')
        ? window.location.hash.slice(1)
        : window.location.hash;
      if (!fragment) {
        setState({ status: 'error', message: 'This share link has no result attached.' });
        return;
      }
      const payload = decodeShare(fragment);
      const run = parseSharedRun(payload.run);
      if (!run) {
        setState({ status: 'error', message: 'This share link uses an unsupported format.' });
        return;
      }
      setState({ status: 'ready', run, projectName: payload.project.name });
    } catch (error) {
      setState({
        status: 'error',
        message:
          error instanceof ShareDecodeError ? error.message : 'This share link could not be read.',
      });
    }
  }, []);

  const content = useMemo(() => {
    if (state.status !== 'ready') return null;
    const { run } = state;
    const storyOutput = sharedStoryOutput(run);
    const storyInput = sharedStoryInput(run);
    const duel = sharedDuel(run);
    const criteria = sharedCriteria(run);
    const testCases = sharedTestCases(run);
    return { run, storyOutput, storyInput, duel, criteria, testCases };
  }, [state]);

  // Gap chips from the viewer's own suite for the same project, when present.
  useEffect(() => {
    if (!content?.testCases || state.status !== 'ready') return;
    const cases = content.testCases.test_cases;
    const suiteId = `suite-${projectSlug(state.projectName)}`;
    let cancelled = false;
    void getSuite(suiteId)
      .then((stored) => {
        if (cancelled || !stored) return;
        setSuiteMatches(
          matchSuite(
            cases.map((c) => ({ id: c.id, title: c.title, expected_result: c.expected_result })),
            stored.rows,
          ),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [content, state]);

  return (
    <div className="min-h-screen bg-bg text-text" data-hydrated={hydrated ? 'true' : undefined}>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center px-4 py-3">
          <Link href="/requirements" className="font-display text-[15px] font-semibold">
            QA-Genius
          </Link>
          <span className="ml-2 text-[12px] text-muted">
            The QA workspace that shows its evidence.
          </span>
        </div>
      </header>
      <main className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6">
        {state.status === 'loading' ? (
          <p className="text-[13px] text-muted">Loading shared result…</p>
        ) : state.status === 'error' ? (
          <EmptyState
            icon={FileText}
            headline="Share link could not be read"
            description={state.message}
          />
        ) : content ? (
          <>
            <div className="rounded-[var(--radius-card)] border border-border bg-card p-3">
              <p className="text-[13px]">
                Shared read-only result · {state.projectName} ·{' '}
                {new Date(content.run.updatedAt).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </p>
            </div>
            <RunStepper current={activeStep(content.run)} interactive={false} />
            {content.storyOutput ? (
              <div className="flex flex-col gap-3">
                <StoryResult data={toRecord(content.storyOutput)} isLoading={false} />
                <StoryExports
                  data={toRecord(content.storyOutput)}
                  input={toRecord(content.run.story?.input ?? {})}
                />
              </div>
            ) : null}
            {content.duel && content.storyInput ? (
              <DuelPanel duel={content.duel} storyText={content.storyInput} />
            ) : null}
            {content.criteria.length > 0 ? (
              <Card>
                <CardHeader
                  title="Acceptance criteria"
                  actions={<Pill tone="neutral">{content.criteria.length}</Pill>}
                />
                <ul className="flex flex-col gap-2">
                  {content.criteria.map((c) => (
                    <li key={c.id} className="flex items-start gap-2 text-[13px]">
                      <Pill tone="neutral" className="font-mono">
                        {c.id}
                      </Pill>
                      <span className="text-text-2">{c.text}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            {content.testCases ? (
              <div className="flex flex-col gap-3">
                <TestCasesResult
                  data={toRecord(content.testCases)}
                  isLoading={false}
                  suiteMatches={suiteMatches}
                />
                <TestCasesExports
                  data={toRecord(content.testCases)}
                  input={toRecord(content.run.testCases?.input ?? {})}
                />
              </div>
            ) : null}
            <div>
              <Button
                variant="primary"
                onClick={() => {
                  adoptSharedRun(content.run);
                  router.push('/requirements');
                }}
              >
                Open in my workspace
              </Button>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
