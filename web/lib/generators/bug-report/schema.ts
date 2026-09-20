import { z } from 'zod';

export const BugReport = z.object({
  title: z.string(),
  severity: z.string(),
  reproducibility_rate: z.string(),
  environment_details: z.string(),
  steps_to_reproduce: z.array(z.string()),
  actual_result: z.string(),
  expected_result: z.string(),
  suggested_fix: z.string().optional(),
  root_cause_category: z.string().optional(),
  business_impact: z.string().optional(),
  affected_users: z.string().optional(),
  regression_risk: z.string().optional(),
  workaround: z.string().optional(),
  related_areas: z.array(z.string()).optional(),
  screenshot_annotations: z.array(z.string()).optional(),
  jira_labels: z.array(z.string()).optional(),
  suspected_pattern: z.string().optional(),
  related_issues: z.array(z.string()).optional(),
  investigation_steps: z.array(z.string()).optional(),
});

export type BugReport = z.infer<typeof BugReport>;
