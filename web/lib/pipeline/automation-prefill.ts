import type { TestCase } from '@/lib/generators/test-cases/schema';

/** Max scenario characters carried from step 3 into step 4. */
export const PREFILL_LIMIT = 5000;

export type ScenarioPrefill = { text: string; truncated: boolean };

/**
 * Compact text of the selected cases for the Automation step:
 * `"id title: steps joined with '; ' → expected"` per case, blank-line joined.
 */
export function buildScenarioPrefill(cases: TestCase[]): ScenarioPrefill {
  const perCase = cases.map(
    (c) => `${c.id} ${c.title}: ${(c.steps ?? []).join('; ')} → ${c.expected_result}`,
  );
  const full = perCase.join('\n\n');
  if (full.length <= PREFILL_LIMIT) return { text: full, truncated: false };
  return { text: full.slice(0, PREFILL_LIMIT), truncated: true };
}
