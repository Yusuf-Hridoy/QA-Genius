'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight } from 'lucide-react';
import { GeneratorScreen } from '@/components/generators/generator-screen';
import { RunStepper } from '@/components/requirements/run-stepper';
import { CoveragePanel } from '@/components/requirements/coverage-panel';
import { TestCasesRefinePanel } from '@/components/refine/test-cases-refine-panel';
import { ShareButton } from '@/components/share/share-button';
import { usePageInfo } from '@/components/shell/shell-context';
import { useRunStore } from '@/lib/store/run';
import { useProjectStore } from '@/lib/store/project';
import { TestCaseList } from '@/lib/generators/test-cases/schema';
import { TestCasesRequest, DEFAULT_COVERAGE_FOCUS } from '@/lib/generators/test-cases/request';
import { buildScenarioPrefill } from '@/lib/pipeline/automation-prefill';
import { TestCasesResult } from '@/components/results/test-cases-result';
import type { StreamMeta } from '@/lib/client/use-object-stream';
import { Button } from '@/components/ui/button';
import { TEST_CASES_AUTOSUBMIT_KEY } from '@/lib/pipeline/keys';
import { SuitePanel } from '@/components/suite/suite-panel';
import { SuiteUploadDialog } from '@/components/suite/suite-upload-dialog';
import { getSuite } from '@/lib/suite/db';
import { matchSuite, type SuiteMatch } from '@/lib/suite/match';
import { projectSlug } from '@/lib/exports/download';
import { downloadTestCasesCsv } from '@/lib/exports/csv';
import { downloadTestCasesXlsx } from '@/lib/exports/xlsx';

function readAutosubmit(): Record<string, unknown> | undefined {
  try {
    const raw = window.sessionStorage.getItem(TEST_CASES_AUTOSUBMIT_KEY);
    window.sessionStorage.removeItem(TEST_CASES_AUTOSUBMIT_KEY);
    if (!raw) return undefined;
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

/** Step 3 — Test cases with traceability, coverage, refine, share, and suite gaps. */
export default function TestCasesStepPage() {
  usePageInfo({ workspace: 'Requirements', tab: 'Test cases' });
  const router = useRouter();
  const run = useRunStore((s) => s.run);
  const setTestCases = useRunStore((s) => s.setTestCases);
  const setSelectedIds = useRunStore((s) => s.setSelectedIds);
  const setAutomationPrefill = useRunStore((s) => s.setAutomationPrefill);
  const project = useProjectStore((s) => s.project);

  const [formKey, setFormKey] = useState(0);
  const [autoSubmit, setAutoSubmit] = useState<Record<string, unknown> | undefined>(undefined);
  const [gapsOnly, setGapsOnly] = useState(false);
  const [refinePreset, setRefinePreset] = useState<{ text: string; nonce: number } | null>(null);
  const [suiteOpen, setSuiteOpen] = useState(false);
  const [suiteMatches, setSuiteMatches] = useState<Record<string, SuiteMatch> | undefined>(
    undefined,
  );
  const consumedAutosubmit = useRef(false);

  const suiteId = `suite-${projectSlug(project.name)}`;

  // Recompute suite matches when the accepted output or the suite changes.
  const outputCasesForMatch = useRunStore((s) => s.run.testCases?.output?.test_cases);
  const suiteSummary = useRunStore((s) => s.run.suite);
  useEffect(() => {
    let cancelled = false;
    if (!outputCasesForMatch || outputCasesForMatch.length === 0) {
      setSuiteMatches(undefined);
      return;
    }
    void getSuite(suiteId)
      .then((stored) => {
        if (cancelled) return;
        if (!stored) {
          setSuiteMatches(undefined);
          return;
        }
        setSuiteMatches(
          matchSuite(
            outputCasesForMatch.map((c) => ({
              id: c.id,
              title: c.title,
              expected_result: c.expected_result,
            })),
            stored.rows,
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setSuiteMatches(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [outputCasesForMatch, suiteSummary, suiteId]);

  useEffect(() => {
    // StrictMode mounts twice in dev: consume the one-shot handoff key once.
    if (consumedAutosubmit.current) return;
    consumedAutosubmit.current = true;
    setAutoSubmit(readAutosubmit());
  }, []);

  const criteriaItems = useMemo(() => run.criteria?.items ?? [], [run.criteria]);
  const storyText = run.story?.input.user_story ?? run.criteria?.manualStory ?? '';

  const initialValues = useMemo<Record<string, unknown>>(() => {
    const prev = run.testCases?.input;
    return {
      user_story: prev?.user_story ?? storyText,
      coverage_focus: prev?.coverage_focus ?? [...DEFAULT_COVERAGE_FOCUS],
      ...(prev?.tech_stack ? { tech_stack: prev.tech_stack } : {}),
      ...(criteriaItems.length > 0
        ? { criteria: criteriaItems.map((c) => ({ id: c.id, text: c.text })) }
        : {}),
    };
  }, [run.testCases?.input, storyText, criteriaItems]);

  const formSummary = useMemo(() => {
    const focus = (run.testCases?.input.coverage_focus ?? [...DEFAULT_COVERAGE_FOCUS]).join(', ');
    const stack = run.testCases?.input.tech_stack || project.stack || 'Not provided';
    const source = run.story?.input ? 'From story' : 'From scratch';
    const criteriaPart =
      criteriaItems.length > 0
        ? ` · ${criteriaItems.length} acceptance ${criteriaItems.length === 1 ? 'criterion' : 'criteria'}`
        : '';
    return `${source}${criteriaPart} · ${focus} · ${stack}`;
  }, [run.testCases?.input, run.story?.input, criteriaItems.length, project.stack]);

  const onResult = useCallback(
    (output: Record<string, unknown>, input: Record<string, unknown>, meta: StreamMeta) => {
      // The handoff request is one-shot: clear it so a later remount resubmits nothing.
      setAutoSubmit(undefined);
      const parsedInput = TestCasesRequest.safeParse(input);
      const parsedOutput = TestCaseList.safeParse(output);
      if (!parsedInput.success || !parsedOutput.success) return;
      setTestCases(parsedInput.data, parsedOutput.data, {
        provider: meta.provider,
        model: meta.model,
        tier: meta.tier,
        requestId: meta.requestId,
        latencyMs: meta.latencyMs,
        repaired: meta.repaired,
      });
    },
    [setTestCases],
  );

  /** Coverage recovery: opens the refine loop with covering instructions. */
  const openUncoveredRefine = useCallback((instructions: string) => {
    setRefinePreset({ text: instructions, nonce: Date.now() });
  }, []);

  /** Rewrite the screen from the accepted run output (exports follow it). */
  const syncScreenToAccepted = useCallback(() => {
    try {
      const output = useRunStore.getState().run.testCases?.output;
      if (output) {
        window.sessionStorage.setItem('qag.result.test_cases', JSON.stringify(output));
      }
    } catch {
      // storage unavailable — the remount still refreshes the view
    }
    setFormKey((k) => k + 1);
  }, []);

  const onCriterionClick = useCallback(
    (id: string) => {
      router.push(`/requirements/criteria?highlight=${encodeURIComponent(id)}`);
    },
    [router],
  );

  const toggleSelect = useCallback(
    (id: string) => {
      const current = run.testCases?.selectedIds ?? [];
      setSelectedIds(current.includes(id) ? current.filter((s) => s !== id) : [...current, id]);
    },
    [run.testCases?.selectedIds, setSelectedIds],
  );

  const outputCases = useMemo(
    () => run.testCases?.output?.test_cases ?? [],
    [run.testCases?.output],
  );
  const selectedIds = run.testCases?.selectedIds ?? [];
  const selectedCases = outputCases.filter((c) => selectedIds.includes(c.id));

  const prefillAutomation = useCallback(() => {
    if (selectedCases.length === 0) return;
    const { text, truncated } = buildScenarioPrefill(selectedCases);
    setAutomationPrefill(text, truncated);
    router.push('/requirements/automation');
  }, [selectedCases, setAutomationPrefill, router]);

  const gapCases = useMemo(() => {
    if (!suiteMatches) return [];
    return outputCases.filter((c) => suiteMatches[c.id]?.status === 'gap');
  }, [suiteMatches, outputCases]);

  const suiteCounts = useMemo(() => {
    if (!suiteMatches || outputCases.length === 0) return null;
    const covered = outputCases.filter((c) => suiteMatches[c.id]?.status === 'covered').length;
    return { covered, gap: gapCases.length, total: outputCases.length };
  }, [suiteMatches, outputCases, gapCases.length]);

  const exportGaps = useCallback(
    (format: 'csv' | 'xlsx') => {
      const output = useRunStore.getState().run.testCases?.output;
      const matches = suiteMatches;
      if (!output || !matches) return;
      const gaps = output.test_cases.filter((c) => matches[c.id]?.status === 'gap');
      if (gaps.length === 0) return;
      const slug = `${projectSlug(project.name)}-gaps`;
      const subset = {
        ...output,
        test_cases: gaps,
        summary: { ...output.summary, total_generated: gaps.length },
      };
      if (format === 'csv') downloadTestCasesCsv(subset, slug);
      else downloadTestCasesXlsx(subset, slug);
    },
    [suiteMatches, project.name],
  );

  return (
    <div className="flex flex-col gap-4">
      <RunStepper current="test-cases" />
      <GeneratorScreen
        key={`test-cases-${formKey}`}
        kind="test_cases"
        initialValues={autoSubmit ?? initialValues}
        autoSubmitOnMount={autoSubmit}
        formSummary={formSummary}
        onResult={onResult}
        restoredResult={run.testCases?.output as unknown as Record<string, unknown> | undefined}
        renderResult={({ data, isLoading }) => (
          <>
            {criteriaItems.length > 0 ? (
              <CoveragePanel
                criteriaIds={criteriaItems.map((c) => c.id)}
                cases={(data?.test_cases as Array<{ traceability: string }> | undefined) ?? []}
                onGenerateUncovered={openUncoveredRefine}
              />
            ) : null}
            <TestCasesRefinePanel onAccepted={syncScreenToAccepted} preset={refinePreset} />
            <TestCasesResult
              data={data}
              isLoading={isLoading}
              selection={{ selected: selectedIds, onToggle: toggleSelect }}
              suiteMatches={suiteMatches}
              gapsOnly={gapsOnly}
              onGapsOnlyChange={setGapsOnly}
              onCriterionClick={onCriterionClick}
            />
          </>
        )}
        resultFooter={
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                onClick={prefillAutomation}
                disabled={selectedCases.length === 0}
              >
                Generate automation for selected
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Button>
              {run.testCases?.output ? <ShareButton run={run} project={project} /> : null}
              {selectedCases.length === 0 && outputCases.length > 0 ? (
                <p className="text-[12px] text-muted">
                  Select at least one case to prefill automation.
                </p>
              ) : null}
            </div>
            {run.testCases?.output ? (
              <SuitePanel
                fileName={suiteSummary?.fileName}
                rowCount={suiteSummary?.count}
                covered={suiteCounts?.covered ?? 0}
                gap={suiteCounts?.gap ?? 0}
                total={suiteCounts?.total ?? 0}
                onUpload={() => setSuiteOpen(true)}
                onExportGapsCsv={() => exportGaps('csv')}
                onExportGapsXlsx={() => exportGaps('xlsx')}
              />
            ) : null}
          </>
        }
      />
      <SuiteUploadDialog
        open={suiteOpen}
        onOpenChange={setSuiteOpen}
        suiteId={suiteId}
        onImported={() => setGapsOnly(false)}
      />
    </div>
  );
}
