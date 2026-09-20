'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight } from 'lucide-react';
import { CriteriaEditor } from '@/components/requirements/criteria-editor';
import { RunStepper } from '@/components/requirements/run-stepper';
import { usePageInfo } from '@/components/shell/shell-context';
import { useRunStore } from '@/lib/store/run';
import { DEFAULT_COVERAGE_FOCUS } from '@/lib/generators/test-cases/request';
import { TEST_CASES_AUTOSUBMIT_KEY } from '@/lib/pipeline/keys';
import { Button } from '@/components/ui/button';

/** Step 2 — Acceptance criteria editor, then hand off to test-case generation. */
export default function CriteriaStepPage() {
  usePageInfo({ workspace: 'Requirements', tab: 'Acceptance criteria' });
  const router = useRouter();
  const run = useRunStore((s) => s.run);
  const setTestCases = useRunStore((s) => s.setTestCases);
  const setManualStory = useRunStore((s) => s.setManualStory);

  const hasStory = run.story?.input !== undefined;
  const items = useMemo(() => run.criteria?.items ?? [], [run.criteria]);
  const manualStory = run.criteria?.manualStory ?? '';

  const storyText = hasStory ? (run.story?.input.user_story ?? '') : manualStory;
  const canGenerate = items.length > 0 && storyText.trim().length >= 30;

  // Traceability chips in step 3 link here with ?highlight=AC-n.
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('highlight');
    if (!id) return;
    setHighlightId(id);
    const t = window.setTimeout(() => {
      rowRefs.current.get(id)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 100);
    return () => window.clearTimeout(t);
  }, []);

  const generateTestCases = useCallback(() => {
    if (!canGenerate) return;
    const prev = run.testCases?.input;
    const input = {
      user_story: storyText.trim(),
      coverage_focus: prev?.coverage_focus ?? [...DEFAULT_COVERAGE_FOCUS],
      ...(prev?.tech_stack ? { tech_stack: prev.tech_stack } : {}),
      criteria: items.map((c) => ({ id: c.id, text: c.text })),
    };
    setTestCases(input);
    try {
      window.sessionStorage.setItem(TEST_CASES_AUTOSUBMIT_KEY, JSON.stringify(input));
    } catch {
      // storage unavailable — step 3 falls back to manual Generate
    }
    router.push('/requirements/test-cases');
  }, [canGenerate, run.testCases, storyText, items, setTestCases, router]);

  return (
    <div className="flex flex-col gap-4">
      <RunStepper current="criteria" />
      {hasStory ? (
        <p className="text-[13px] text-text-2">
          From story · {items.length} acceptance {items.length === 1 ? 'criterion' : 'criteria'}
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="manual-story" className="text-[13px] font-medium">
            Story
          </label>
          <textarea
            id="manual-story"
            value={manualStory}
            onChange={(e) => setManualStory(e.target.value)}
            rows={4}
            placeholder="As a shopper, I want to save items for later so I can buy them next visit."
            className="w-full rounded-[var(--radius)] border border-border bg-card px-2.5 py-2 text-[13px] text-text focus-visible:outline-none"
          />
          <p className="text-[12px] text-muted">
            Start from scratch: describe the story, then list criteria below.
          </p>
        </div>
      )}
      <CriteriaEditor highlightId={highlightId} rowRefs={rowRefs} />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={generateTestCases} disabled={!canGenerate}>
          Generate test cases
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Button>
        {!canGenerate ? (
          <p className="text-[12px] text-muted">
            Add at least one criterion and a story of 30 or more characters.
          </p>
        ) : null}
      </div>
    </div>
  );
}
