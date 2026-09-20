import { z } from 'zod';

export const STORY_TYPES = [
  'User Story',
  'Technical Story',
  'Bug Fix Story',
  'Spike/Research',
] as const;

export const StoryAnalyzerRequest = z.object({
  user_story: z.string().trim().min(20).max(3000),
  story_type: z.enum(STORY_TYPES).default('User Story'),
  project_context: z.string().trim().max(1000).optional(),
  instructions: z.string().trim().max(1000).optional(),
});

export type StoryAnalyzerRequest = z.infer<typeof StoryAnalyzerRequest>;
