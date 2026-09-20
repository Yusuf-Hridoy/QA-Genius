import { applyGlobalRules } from '@/lib/prompts/global-rules';
import { formatInstructions } from '@/lib/prompts/format';
import { StoryInterpretation } from './schema';
import type { StoryInterpretationRequest } from './request';

const PERSONA_LINE = {
  A: 'You prefer the strictest reading: narrow scope, short deadlines, exact numbers, no implied features.',
  B: 'You prefer the most permissive reading: broad scope, generous deadlines, flexible numbers, helpful implied features.',
} as const;

/**
 * System prompt for the Ambiguity Duel interpretations (Phase 2, new — not v1).
 * The model commits to one concrete reading and invents specific numbers
 * where the story is vague, so the two personas can be diffed.
 */
function baseSystem(persona: 'A' | 'B'): string {
  return (
    `You are a senior QA engineer reading a user story exactly once. ` +
    `Commit to the single most likely concrete interpretation. ` +
    `Where the story is vague, invent specific numbers, actors, and timings — do not list alternatives. ` +
    PERSONA_LINE[persona] +
    `\nFor every rule and number, copy the "sourcePhrase" EXACTLY as it appears in the story text ` +
    `(a verbatim substring, including the same words and punctuation). ` +
    `Never paraphrase the source phrase.`
  );
}

export function buildStoryInterpretationPrompt(req: StoryInterpretationRequest): {
  system: string;
  user: string;
} {
  const system = applyGlobalRules(
    `${baseSystem(req.persona)}\n${formatInstructions(StoryInterpretation)}`,
    false,
  );
  const user =
    `Story Type: ${req.story_type || 'User Story'}\n` +
    `Project Context: ${req.project_context || 'Not provided'}\n\n` +
    `User Story:\n${req.user_story}\n\n` +
    `Persona: ${req.persona}`;
  return { system, user };
}
