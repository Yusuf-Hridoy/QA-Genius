import type { TestCase, TestCaseList } from '@/lib/generators/test-cases/schema';
import { dateStamp, downloadText } from './download';

/** Models escape newlines as the two-character sequence \n inside BDD strings. */
function unfoldNewlines(text: string): string {
  return text.replace(/\\n/g, '\n');
}

function scenarioBody(tc: TestCase): string {
  if (tc.bdd_scenario) {
    const lines = unfoldNewlines(tc.bdd_scenario)
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => '    ' + line);
    // ensure a Scenario title exists
    if (lines.some((line) => line.trim().startsWith('Scenario:'))) {
      return lines.join('\n');
    }
    return [`    Scenario: ${tc.title}`, ...lines].join('\n');
  }
  // Fallback: pre_conditions → Given, steps → When, expected → Then.
  const lines = [`    Scenario: ${tc.title}`];
  if (tc.pre_conditions) {
    lines.push(`    Given ${tc.pre_conditions}`);
  }
  for (const step of tc.steps) {
    lines.push(`    When ${step}`);
  }
  lines.push(`    Then ${tc.expected_result}`);
  return lines.join('\n');
}

/** One Feature block titled from the story's first line, one Scenario per case. */
export function testCasesToFeature(result: TestCaseList, storyTitle: string): string {
  const title = storyTitle.trim().split('\n')[0]?.trim() || 'Generated test cases';
  const blocks = result.test_cases.map((tc) => scenarioBody(tc));
  return `Feature: ${title}\n\n${blocks.join('\n\n')}\n`;
}

export function downloadFeature(result: TestCaseList, storyTitle: string, slug: string) {
  downloadText(
    `${slug}-test-cases-${dateStamp()}.feature`,
    testCasesToFeature(result, storyTitle),
    'text/plain',
  );
}
