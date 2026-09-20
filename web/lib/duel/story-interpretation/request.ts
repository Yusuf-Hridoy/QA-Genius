import { z } from 'zod';

export const StoryInterpretationRequest = z.object({
  user_story: z.string().trim().min(20).max(3000),
  story_type: z.string().trim().max(60).optional(),
  project_context: z.string().trim().max(1000).optional(),
  persona: z.enum(['A', 'B']),
});

export type StoryInterpretationRequest = z.infer<typeof StoryInterpretationRequest>;
