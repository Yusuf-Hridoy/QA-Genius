import Papa from 'papaparse';
import type { TestCase, TestCaseList } from '@/lib/generators/test-cases/schema';
import { dateStamp, downloadText } from './download';

export const CSV_HEADERS = [
  'ID',
  'Title',
  'Category',
  'Priority',
  'Pre-conditions',
  'Steps',
  'Expected Result',
  'Test Data',
  'BDD Scenario',
  'Automation Feasibility',
  'Automation Effort',
  'Tags',
  'Traceability',
] as const;

export function testCaseToRow(tc: TestCase): Record<(typeof CSV_HEADERS)[number], string> {
  return {
    ID: tc.id,
    Title: tc.title,
    Category: tc.category,
    Priority: tc.priority,
    'Pre-conditions': tc.pre_conditions,
    Steps: tc.steps.map((step, i) => `${i + 1}. ${step}`).join('\n'),
    'Expected Result': tc.expected_result,
    'Test Data': tc.test_data ?? '',
    'BDD Scenario': tc.bdd_scenario ?? '',
    'Automation Feasibility': tc.automation_feasibility,
    'Automation Effort': tc.automation_effort,
    Tags: tc.tags.join('; '),
    Traceability: tc.traceability,
  };
}

/** CSV with UTF-8 BOM so Excel opens it correctly. */
export function testCasesToCsv(result: TestCaseList): string {
  const rows = result.test_cases.map(testCaseToRow);
  const csv = Papa.unparse({
    fields: [...CSV_HEADERS],
    data: rows.map((r) => CSV_HEADERS.map((h) => r[h])),
  });
  return '\uFEFF' + csv;
}

export function downloadTestCasesCsv(result: TestCaseList, slug: string) {
  downloadText(`${slug}-test-cases-${dateStamp()}.csv`, testCasesToCsv(result), 'text/csv');
}
