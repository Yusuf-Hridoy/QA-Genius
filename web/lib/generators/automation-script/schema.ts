import { z } from 'zod';

export const AutomationScript = z.object({
  framework: z.string(),
  project_structure: z.array(z.string()),
  page_object_file_name: z.string().optional(),
  page_object_code: z.string().optional(),
  test_file_name: z.string(),
  test_code: z.string(),
  conftest_file_name: z.string().optional(),
  conftest_code: z.string().optional(),
  config_file_name: z.string().optional(),
  config_code: z.string().optional(),
  requirements_txt: z.string().optional(),
  setup_instructions: z.array(z.string()),
  execution_command: z.string(),
  design_notes: z.string().optional(),
});

export type AutomationScript = z.infer<typeof AutomationScript>;
