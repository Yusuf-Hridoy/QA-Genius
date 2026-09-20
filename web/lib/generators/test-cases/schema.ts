import { z } from 'zod';

export const CategoryCount = z.object({
  category: z.string(),
  count: z.number().int(),
});

export const PriorityCount = z.object({
  priority: z.string(),
  count: z.number().int(),
});

export const TestSuiteSummary = z.object({
  total_generated: z.number().int(),
  category_breakdown: z.array(CategoryCount),
  priority_breakdown: z.array(PriorityCount),
  automation_coverage_potential: z.string(),
  coverage_gaps: z.array(z.string()),
  recommendations: z.array(z.string()),
});

export const TestCase = z.object({
  id: z.string(),
  title: z.string(),
  category: z.string(),
  pre_conditions: z.string(),
  steps: z.array(z.string()),
  expected_result: z.string(),
  priority: z.string(),
  test_data: z.string().optional(),
  bdd_scenario: z.string().optional(),
  automation_feasibility: z.string(),
  automation_effort: z.string(),
  tags: z.array(z.string()),
  traceability: z.string(),
});

export const TestCaseList = z.object({
  test_cases: z.array(TestCase),
  summary: TestSuiteSummary,
});

export type TestCase = z.infer<typeof TestCase>;
export type TestSuiteSummary = z.infer<typeof TestSuiteSummary>;
export type TestCaseList = z.infer<typeof TestCaseList>;
