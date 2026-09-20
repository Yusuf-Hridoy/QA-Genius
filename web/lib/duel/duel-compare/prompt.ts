import { applyGlobalRules } from '@/lib/prompts/global-rules';
import { formatInstructions } from '@/lib/prompts/format';
import { DuelCompareOutput } from './schema';
import type { DuelCompareRequest } from './schema';

/**
 * System prompt for the duel comparison (Phase 2, new — not v1). Diffs two
 * committed interpretations into forks (disagreements tied to a story phrase)
 * and agreements.
 */
const BASE_SYSTEM =
  `You are a senior QA engineer reviewing two independent readings of the same user story. ` +
  `Diff them into forks: every place where the readings disagree about scope, numbers, actors, ` +
  `timing, or behavior becomes one fork. ` +
  `For each fork copy "sourcePhrase" EXACTLY as it appears in the story text (a verbatim substring). ` +
  `Rank severity by rework risk: high means the team would build the wrong thing, ` +
  `medium means extra clarification rounds, low means cosmetic wording. ` +
  `Write each "suggestedRewrite" as a concrete replacement for the source phrase. ` +
  `List genuine agreements separately; do not force agreement where readings differ.`;

export function buildDuelComparePrompt(req: DuelCompareRequest): {
  system: string;
  user: string;
} {
  const system = applyGlobalRules(
    `${BASE_SYSTEM}\n${formatInstructions(DuelCompareOutput)}`,
    false,
  );
  const user =
    `User Story:\n${req.user_story}\n\n` +
    `Reading A:\n${JSON.stringify(req.a)}\n\n` +
    `Reading B:\n${JSON.stringify(req.b)}`;
  return { system, user };
}
