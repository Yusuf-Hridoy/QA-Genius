import { z } from 'zod';
import { StoryInterpretation } from '../story-interpretation/schema';

export const DuelFork = z.object({
  topic: z.string(),
  readingA: z.string(),
  readingB: z.string(),
  sourcePhrase: z.string(),
  severity: z.enum(['high', 'medium', 'low']),
  suggestedRewrite: z.string(),
});

export const DuelCompareOutput = z.object({
  forks: z.array(DuelFork),
  agreements: z.array(z.string()),
});

export type DuelCompareOutput = z.infer<typeof DuelCompareOutput>;

export const DuelCompareRequest = z.object({
  user_story: z.string().trim().min(20).max(3000),
  a: StoryInterpretation,
  b: StoryInterpretation,
});

export type DuelCompareRequest = z.infer<typeof DuelCompareRequest>;
