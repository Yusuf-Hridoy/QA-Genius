import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { TestCaseList } from '@/lib/generators/test-cases/schema';
import { BugReport } from '@/lib/generators/bug-report/schema';
import { AutomationScript } from '@/lib/generators/automation-script/schema';
import { StoryAnalyzerRequest } from '@/lib/generators/story-analyzer/request';
import { TestCasesRequest } from '@/lib/generators/test-cases/request';
import { BugReportRequest } from '@/lib/generators/bug-report/request';
import { AutomationRequest } from '@/lib/generators/automation-script/request';

const FIXTURES = join(__dirname, '..', '..', 'fixtures');

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function fixtureDir(kind: string): string[] {
  return readdirSync(join(FIXTURES, kind))
    .filter((f) => f.startsWith('input-'))
    .sort();
}

describe('sample outputs parse against their schemas', () => {
  it('story_analyzer sample-output.json', () => {
    expect(() =>
      AmbiguityAnalysis.parse(readJson(join(FIXTURES, 'story_analyzer', 'sample-output.json'))),
    ).not.toThrow();
  });

  it('test_cases sample-output.json', () => {
    const parsed = TestCaseList.parse(readJson(join(FIXTURES, 'test_cases', 'sample-output.json')));
    expect(parsed.test_cases.length).toBeGreaterThanOrEqual(8);
    expect(parsed.summary.total_generated).toBe(parsed.test_cases.length);
  });

  it('bug_report sample-output.json', () => {
    expect(() =>
      BugReport.parse(readJson(join(FIXTURES, 'bug_report', 'sample-output.json'))),
    ).not.toThrow();
  });

  it('automation_script sample-output.json', () => {
    expect(() =>
      AutomationScript.parse(readJson(join(FIXTURES, 'automation_script', 'sample-output.json'))),
    ).not.toThrow();
  });

  it('strips unknown fields', () => {
    const parsed = BugReport.parse({
      title: 't',
      severity: 'Low',
      reproducibility_rate: 'Always',
      environment_details: 'Staging',
      steps_to_reproduce: ['Open checkout'],
      actual_result: 'Broken',
      expected_result: 'Works',
      unexpected_field: 1,
    });
    expect(parsed).not.toHaveProperty('unexpected_field');
  });
});

describe('fixture inputs validate against their request schemas', () => {
  it('story_analyzer inputs', () => {
    for (const file of fixtureDir('story_analyzer')) {
      expect(() =>
        StoryAnalyzerRequest.parse(readJson(join(FIXTURES, 'story_analyzer', file))),
      ).not.toThrow();
    }
  });

  it('test_cases inputs', () => {
    for (const file of fixtureDir('test_cases')) {
      const parsed = TestCasesRequest.parse(readJson(join(FIXTURES, 'test_cases', file)));
      expect(parsed.coverage_focus.length).toBeGreaterThan(0);
    }
  });

  it('bug_report inputs', () => {
    for (const file of fixtureDir('bug_report')) {
      expect(() =>
        BugReportRequest.parse(readJson(join(FIXTURES, 'bug_report', file))),
      ).not.toThrow();
    }
  });

  it('automation_script inputs', () => {
    for (const file of fixtureDir('automation_script')) {
      expect(() =>
        AutomationRequest.parse(readJson(join(FIXTURES, 'automation_script', file))),
      ).not.toThrow();
    }
  });
});

describe('bug request refine', () => {
  it('rejects successful attempts greater than total', () => {
    const result = BugReportRequest.safeParse({
      raw_bug: 'Checkout button does nothing on the second click in Safari',
      total_attempts: 3,
      successful_attempts: 4,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['successful_attempts']);
    }
  });
});
