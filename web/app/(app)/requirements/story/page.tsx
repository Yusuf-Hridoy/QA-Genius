'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Swords } from 'lucide-react';
import { toast } from 'sonner';
import { GeneratorScreen } from '@/components/generators/generator-screen';
import { RunStepper } from '@/components/requirements/run-stepper';
import { DuelPanel } from '@/components/duel/duel-panel';
import { StoryRefinePanel } from '@/components/refine/story-refine-panel';
import { ShareButton } from '@/components/share/share-button';
import { useProjectStore } from '@/lib/store/project';
import { usePageInfo } from '@/components/shell/shell-context';
import { useRunStore } from '@/lib/store/run';
import { useKeysStore } from '@/lib/store/keys';
import { useDefaultKey } from '@/components/shell/key-badge';
import { buildByokHeaders } from '@/lib/llm/byok';
import { showNoKeyToast } from '@/lib/client/api-error';
import { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { StoryAnalyzerRequest } from '@/lib/generators/story-analyzer/request';
import { runDuel, type DuelStage } from '@/lib/duel/run-duel';
import type { StreamMeta } from '@/lib/client/use-object-stream';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/pill';
import storyExample from '@/fixtures/story_analyzer/input-1.json';

type Source = 'paste' | 'example';

/** Step 1 — Story analyzer, plus the duel entry point and the step 2 handoff. */
export default function StoryStepPage() {
  usePageInfo({ workspace: 'Requirements', tab: 'Story' });
  const router = useRouter();
  const run = useRunStore((s) => s.run);
  const setStory = useRunStore((s) => s.setStory);
  const setCriteria = useRunStore((s) => s.setCriteria);
  const setDuel = useRunStore((s) => s.setDuel);
  const project = useProjectStore((s) => s.project);
  const defaultKey = useDefaultKey();
  const tier = useKeysStore((s) => s.tier);

  const [source, setSource] = useState<Source>('paste');
  const [formKey, setFormKey] = useState(0);
  const [exampleValues, setExampleValues] = useState<Record<string, unknown> | undefined>(
    undefined,
  );
  const [edited, setEdited] = useState(false);
  const [duelRunning, setDuelRunning] = useState(false);
  const [duelStarted, setDuelStarted] = useState(false);
  const [stages, setStages] = useState<Record<DuelStage, boolean>>({
    A: false,
    B: false,
    compare: false,
  });

  const onResult = useCallback(
    (output: Record<string, unknown>, input: Record<string, unknown>, meta: StreamMeta) => {
      const parsedInput = StoryAnalyzerRequest.safeParse(input);
      const parsedOutput = AmbiguityAnalysis.safeParse(output);
      if (!parsedInput.success || !parsedOutput.success) return;
      setStory(parsedInput.data, parsedOutput.data, {
        provider: meta.provider,
        model: meta.model,
        tier: meta.tier,
        requestId: meta.requestId,
        latencyMs: meta.latencyMs,
        repaired: meta.repaired,
      });
    },
    [setStory],
  );

  const pickSource = useCallback((next: Source) => {
    setSource(next);
    setExampleValues(next === 'example' ? (storyExample as Record<string, unknown>) : undefined);
    setEdited(false);
    setFormKey((k) => k + 1);
  }, []);

  const acceptance = useMemo(
    () => run.story?.output?.generated_acceptance_criteria ?? [],
    [run.story?.output],
  );
  const canHandOff = acceptance.length > 0;

  const handOff = useCallback(() => {
    if (!canHandOff) return;
    setCriteria(acceptance, 'story');
    router.push('/requirements/criteria');
  }, [canHandOff, acceptance, setCriteria, router]);

  const canDuel = run.story?.input !== undefined && !duelRunning;

  const startDuel = useCallback(async () => {
    const input = useRunStore.getState().run.story?.input;
    if (!input) return;
    if (!defaultKey) {
      showNoKeyToast();
      return;
    }
    setDuelRunning(true);
    setDuelStarted(true);
    setStages({ A: false, B: false, compare: false });
    try {
      const duel = await runDuel({
        userStory: input.user_story,
        storyType: input.story_type,
        projectContext: input.project_context,
        headers: buildByokHeaders(defaultKey, tier),
        onStage: (stage, done) => setStages((prev) => ({ ...prev, [stage]: done })),
      });
      setDuel(duel);
    } catch (error) {
      // Failures leave the panel in its previous state.
      toast.error(error instanceof Error ? error.message : 'The duel failed. Try again.');
    } finally {
      setDuelRunning(false);
    }
  }, [defaultKey, tier, setDuel]);

  const applyRewrite = useCallback((sourcePhrase: string, suggestedRewrite: string) => {
    const input = useRunStore.getState().run.story?.input;
    if (!input) return;
    const at = input.user_story.toLowerCase().indexOf(sourcePhrase.toLowerCase());
    if (at === -1) return;
    const next =
      input.user_story.slice(0, at) +
      suggestedRewrite +
      input.user_story.slice(at + sourcePhrase.length);
    setExampleValues({ ...input, user_story: next });
    setSource('paste');
    setEdited(true);
    setFormKey((k) => k + 1);
  }, []);

  /** Rewrite the screen from the accepted run output (exports follow it). */
  const syncStoryScreen = useCallback(() => {
    try {
      const output = useRunStore.getState().run.story?.output;
      if (output) {
        window.sessionStorage.setItem('qag.result.story_analyzer', JSON.stringify(output));
      }
    } catch {
      // storage unavailable — the remount still refreshes the view
    }
    setFormKey((k) => k + 1);
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <RunStepper current="story" />
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Story source">
        <span className="mr-1 text-[11px] font-medium uppercase tracking-wide text-muted">
          Source
        </span>
        <button
          type="button"
          onClick={() => pickSource('paste')}
          aria-pressed={source === 'paste'}
          className={
            source === 'paste'
              ? 'rounded-full border border-accent bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent'
              : 'rounded-full border border-border-strong bg-card px-2.5 py-1 text-[11px] font-medium text-text-2 hover:bg-card-2'
          }
        >
          Paste
        </button>
        <button
          type="button"
          onClick={() => pickSource('example')}
          aria-pressed={source === 'example'}
          className={
            source === 'example'
              ? 'rounded-full border border-accent bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent'
              : 'rounded-full border border-border-strong bg-card px-2.5 py-1 text-[11px] font-medium text-text-2 hover:bg-card-2'
          }
        >
          Load example
        </button>
      </div>
      <GeneratorScreen
        key={`story-${formKey}`}
        kind="story_analyzer"
        initialValues={exampleValues}
        onResult={onResult}
        restoredResult={run.story?.output as unknown as Record<string, unknown> | undefined}
        resultHeader={
          <>
            {run.duel && run.story?.input ? (
              <DuelPanel
                duel={run.duel}
                storyText={run.story.input.user_story}
                onApplyRewrite={applyRewrite}
              />
            ) : null}
            <StoryRefinePanel onAccepted={syncStoryScreen} />
            {run.story?.output ? (
              <div className="flex flex-wrap items-center gap-2">
                <ShareButton run={run} project={project} />
              </div>
            ) : null}
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={startDuel} disabled={!canDuel} loading={duelRunning}>
          <Swords className="h-3.5 w-3.5" aria-hidden />
          Run ambiguity duel
        </Button>
        <Button variant="primary" onClick={handOff} disabled={!canHandOff}>
          Use these acceptance criteria
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[12px] text-muted">Runs 3 short model calls.</p>
        {duelStarted ? (
          <div className="flex items-center gap-1.5" aria-label="Duel progress">
            {(['A', 'B', 'compare'] as DuelStage[]).map((stage) => (
              <Pill key={stage} tone={stages[stage] ? 'ok' : 'neutral'}>
                {stage === 'compare' ? 'Compare' : `Reading ${stage}`}
              </Pill>
            ))}
          </div>
        ) : null}
        {edited ? (
          <p className="text-[12px] text-muted">
            Story edited from a duel rewrite. Generate again to re-analyze.
          </p>
        ) : null}
      </div>
    </div>
  );
}
