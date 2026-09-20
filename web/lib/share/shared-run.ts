import { z } from 'zod';
import { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { TestCaseList } from '@/lib/generators/test-cases/schema';
import { StoryInterpretation } from '@/lib/duel/story-interpretation/schema';
import { DuelFork } from '@/lib/duel/duel-compare/schema';
import type { AcceptanceCriterion, Run } from '@/lib/pipeline/types';
import type { DuelResult } from '@/lib/duel/types';

const SharedDuelResult = z.object({
  a: StoryInterpretation,
  b: StoryInterpretation,
  forks: z.array(DuelFork),
  agreements: z.array(z.string()),
  agreementRatio: z.number(),
  highlights: z.array(
    z.object({
      phrase: z.string(),
      forkIndex: z.number().int(),
      start: z.number().int(),
      end: z.number().int(),
    }),
  ),
});

const SharedCriterion = z.object({ id: z.string(), text: z.string() });

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

/** Lenient shape check for a decoded run (envelope already validated). */
export function parseSharedRun(value: unknown): Run | null {
  const raw = asRecord(value);
  if (typeof raw.id !== 'string') return null;
  return value as Run;
}

export function sharedStoryOutput(run: Run): AmbiguityAnalysis | undefined {
  const parsed = AmbiguityAnalysis.safeParse(run.story?.output);
  return parsed.success ? parsed.data : undefined;
}

export function sharedStoryInput(run: Run): string | undefined {
  const input = asRecord(run.story?.input);
  return typeof input.user_story === 'string' ? input.user_story : undefined;
}

export function sharedCriteria(run: Run): AcceptanceCriterion[] {
  const items = asRecord(run.criteria).items;
  const parsed = z.array(SharedCriterion).safeParse(items);
  return parsed.success ? parsed.data : [];
}

export function sharedTestCases(run: Run): TestCaseList | undefined {
  const parsed = TestCaseList.safeParse(run.testCases?.output);
  return parsed.success ? parsed.data : undefined;
}

export function sharedDuel(run: Run): DuelResult | undefined {
  const parsed = SharedDuelResult.safeParse(run.duel);
  return parsed.success ? parsed.data : undefined;
}
