import { z } from 'zod';

export const VaguePhrase = z.object({
  phrase: z.string(),
  severity: z.string(),
  suggestion: z.string(),
  replacement: z.string(),
});

export const AmbiguityAnalysis = z.object({
  ambiguity_score: z.number().int(),
  clarity_label: z.string(),
  invest_overall: z.string(),
  invest_independent: z.string(),
  invest_negotiable: z.string(),
  invest_valuable: z.string(),
  invest_estimable: z.string(),
  invest_small: z.string(),
  invest_testable: z.string(),
  vague_phrases: z.array(VaguePhrase),
  missing_elements: z.array(z.string()),
  suggested_rewrites: z.array(z.string()),
  generated_acceptance_criteria: z.array(z.string()),
  risks: z.array(z.string()),
  score_breakdown: z.string().optional(),
  recommended_split: z.array(z.string()).optional(),
});

export type VaguePhrase = z.infer<typeof VaguePhrase>;
export type AmbiguityAnalysis = z.infer<typeof AmbiguityAnalysis>;
