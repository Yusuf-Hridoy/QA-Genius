import { z } from 'zod';

export const FRAMEWORKS = [
  'Playwright (Python)',
  'Playwright (JavaScript)',
  'Selenium (Python)',
  'Cypress (JavaScript)',
] as const;

export const LANGUAGES = ['JavaScript', 'TypeScript'] as const;
export const STRUCTURES = ['Flat scripts (no POM)', 'Page Object Model'] as const;
export const BROWSERS = ['Chromium', 'Firefox', 'WebKit'] as const;
export const SITE_TYPES = [
  'Custom (paste URL above)',
  'saucedemo.com',
  'the-internet.herokuapp.com',
  'automationexercise.com',
] as const;

export type Framework = (typeof FRAMEWORKS)[number];
export type Language = (typeof LANGUAGES)[number];

/** True for frameworks whose generated code is Python (Playwright (Python), Selenium (Python)). */
export function isPythonFramework(framework: Framework): boolean {
  return framework.endsWith('(Python)');
}

export const AutomationRequest = z.object({
  scenario: z.string().trim().min(30).max(5000),
  framework: z.enum(FRAMEWORKS).default('Playwright (JavaScript)'),
  language: z.enum(LANGUAGES).default('TypeScript'),
  structure: z.enum(STRUCTURES).default('Page Object Model'),
  browsers: z.array(z.enum(BROWSERS)).min(1).default(['Chromium']),
  site_type: z.enum(SITE_TYPES).default('Custom (paste URL above)'),
  instructions: z.string().trim().max(1000).optional(),
  /**
   * Repair loop (Phase 3): the previously generated files, sent back with
   * fix-only instructions. User-prompt only; each file ≤ 20 000 chars.
   */
  previousFiles: z
    .array(z.object({ name: z.string().max(200), code: z.string().max(20_000) }))
    .max(8)
    .optional(),
});

export type AutomationRequest = z.infer<typeof AutomationRequest>;
