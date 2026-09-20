import { z } from 'zod';

export const InterpretationRule = z.object({
  topic: z.string(),
  reading: z.string(),
  sourcePhrase: z.string(),
});

export const InterpretationNumber = z.object({
  name: z.string(),
  value: z.string(),
  sourcePhrase: z.string(),
});

export const StoryInterpretation = z.object({
  actors: z.array(z.string()),
  preconditions: z.array(z.string()),
  rules: z.array(InterpretationRule),
  numbers: z.array(InterpretationNumber),
  outcomes: z.array(z.string()),
  assumptions: z.array(z.string()),
});

export type StoryInterpretation = z.infer<typeof StoryInterpretation>;
