'use client';

import { generateOne } from '@/lib/client/generate-one';
import { StoryInterpretation } from './story-interpretation/schema';
import { DuelCompareOutput } from './duel-compare/schema';
import { agreementRatio, findHighlights } from './highlights';
import type { DuelResult, Interpretation } from './types';

export type DuelStage = 'A' | 'B' | 'compare';

export type DuelRequestMeta = {
  provider?: string;
  model?: string;
  tier?: string;
  requestId?: string;
};

/** POST through the existing generate route, consuming the stream to the final object. */
async function postGenerate(
  kind: string,
  body: unknown,
  headers: Record<string, string>,
): Promise<{ data: unknown; meta: DuelRequestMeta }> {
  return generateOne(kind, body, headers);
}

function toInterpretation(value: unknown, persona: string): Interpretation {
  const parsed = StoryInterpretation.safeParse(value);
  if (!parsed.success) {
    throw new Error(`Reading ${persona} returned output that could not be read. Try again.`);
  }
  return parsed.data;
}

/**
 * Client flow for the Ambiguity Duel: two interpretations in parallel (A and
 * B), then the comparison. Deterministic additions (agreementRatio,
 * highlights) are computed in code.
 */
export async function runDuel(args: {
  userStory: string;
  storyType?: string;
  projectContext?: string;
  headers: Record<string, string>;
  onStage?: (stage: DuelStage, done: boolean) => void;
}): Promise<DuelResult> {
  const { userStory, storyType, projectContext, headers, onStage } = args;
  const base = {
    user_story: userStory,
    ...(storyType ? { story_type: storyType } : {}),
    ...(projectContext ? { project_context: projectContext } : {}),
  };

  onStage?.('A', false);
  onStage?.('B', false);
  const [aRaw, bRaw] = await Promise.all([
    postGenerate('story_interpretation', { ...base, persona: 'A' }, headers).then((r) => {
      onStage?.('A', true);
      return r.data;
    }),
    postGenerate('story_interpretation', { ...base, persona: 'B' }, headers).then((r) => {
      onStage?.('B', true);
      return r.data;
    }),
  ]);
  const a = toInterpretation(aRaw, 'A');
  const b = toInterpretation(bRaw, 'B');

  onStage?.('compare', false);
  const compared = await postGenerate('duel_compare', { user_story: userStory, a, b }, headers);
  onStage?.('compare', true);
  const parsedCompare = DuelCompareOutput.safeParse(compared.data);
  if (!parsedCompare.success) {
    throw new Error('The duel comparison returned output that could not be read. Try again.');
  }
  const { forks, agreements } = parsedCompare.data;
  return {
    a,
    b,
    forks,
    agreements,
    agreementRatio: agreementRatio(agreements.length, forks.length),
    highlights: findHighlights(userStory, forks),
  };
}
