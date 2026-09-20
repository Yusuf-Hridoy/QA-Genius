import { z } from 'zod';

export const COVERAGE_FOCI = [
  'Functional',
  'Negative',
  'Boundary',
  'Edge Case',
  'Accessibility',
  'Security',
  'Performance',
  'Localization',
] as const;

export const DEFAULT_COVERAGE_FOCUS: CoverageFocus[] = [
  'Functional',
  'Negative',
  'Boundary',
  'Edge Case',
];

export type CoverageFocus = (typeof COVERAGE_FOCI)[number];

export const TestCasesRequest = z.object({
  user_story: z.string().trim().min(30).max(5000),
  coverage_focus: z.array(z.enum(COVERAGE_FOCI)).min(1).default(DEFAULT_COVERAGE_FOCUS),
  tech_stack: z.string().trim().max(300).optional(),
  instructions: z.string().trim().max(1000).optional(),
  /** Pipeline criteria injected by step 2 (Phase 2). Referenced in traceability. */
  criteria: z
    .array(z.object({ id: z.string(), text: z.string().trim().max(500) }))
    .max(40)
    .optional(),
  /** Previous output for the refine loop (Phase 2): id + title lines only. */
  previous: z
    .array(z.object({ id: z.string(), title: z.string() }))
    .max(60)
    .optional(),
});

export type TestCasesRequest = z.infer<typeof TestCasesRequest>;
