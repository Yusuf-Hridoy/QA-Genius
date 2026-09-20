import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import Papa from 'papaparse';
import * as XLSX from 'xlsx-js-style';
import { testCasesToCsv, CSV_HEADERS } from '@/lib/exports/csv';
import { testCasesToXlsx, buildTestCasesWorkbook } from '@/lib/exports/xlsx';
import { testCasesToFeature } from '@/lib/exports/feature';
import { storyToMarkdown, bugToMarkdown } from '@/lib/exports/markdown';
import { automationFiles } from '@/lib/exports/zip';
import type { TestCaseList } from '@/lib/generators/test-cases/schema';
import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import type { BugReport } from '@/lib/generators/bug-report/schema';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';

const FIXTURES = join(__dirname, '..', '..', 'fixtures');

function fixture<T>(kind: string, file: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, kind, file), 'utf8')) as T;
}

const testCases = fixture<TestCaseList>('test_cases', 'sample-output.json');
const analysis = fixture<AmbiguityAnalysis>('story_analyzer', 'sample-output.json');
const bug = fixture<BugReport>('bug_report', 'sample-output.json');
const automation = fixture<AutomationScript>('automation_script', 'sample-output.json');

beforeEach(() => {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:mock'),
    revokeObjectURL: vi.fn(),
  });
});

describe('CSV export', () => {
  it('starts with a UTF-8 BOM and has a header plus one row per case', () => {
    const csv = testCasesToCsv(testCases);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    const parsed = Papa.parse<string[]>(csv.slice(1));
    expect(parsed.data[0]?.slice(0, 3)).toEqual(['ID', 'Title', 'Category']);
    expect(parsed.data.length).toBe(testCases.test_cases.length + 1);
  });

  it('uses the v1 column set', () => {
    const csv = testCasesToCsv(testCases);
    for (const header of CSV_HEADERS) {
      expect(csv).toContain(header);
    }
  });
});

describe('XLSX export', () => {
  it('writes a bold frozen header with column widths before serialization', () => {
    const wb = buildTestCasesWorkbook(testCases);
    const sheet = wb.Sheets['Test Cases'];
    if (!sheet) throw new Error('Test Cases sheet missing');
    expect(sheet['!freeze']).toMatchObject({ ySplit: 1 });
    expect(sheet['!cols']).toBeTruthy();
    const headerCell = sheet['A1'] as { v: string; s: { font: { bold: boolean } } };
    expect(headerCell.v).toBe('ID');
    expect(headerCell.s.font.bold).toBe(true);
  });

  it('reopens with the Test Cases and Summary sheets', () => {
    const buffer = testCasesToXlsx(testCases);
    const wb = XLSX.read(buffer, { type: 'array' });
    expect(wb.SheetNames).toEqual(['Test Cases', 'Summary']);
    const sheet = wb.Sheets['Test Cases'];
    if (!sheet) throw new Error('Test Cases sheet missing');
    const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1 });
    expect(rows[0]?.[0]).toBe('ID');
    expect(rows.length).toBe(testCases.test_cases.length + 1);
  });
});

describe('.feature export', () => {
  it('emits one Scenario per test case', () => {
    const feature = testCasesToFeature(testCases, 'Account lockout after failed attempts');
    const scenarios = feature.match(/Scenario:/g) ?? [];
    expect(scenarios.length).toBe(testCases.test_cases.length);
    expect(feature.startsWith('Feature: Account lockout after failed attempts')).toBe(true);
  });

  it('falls back to Given/When/Then when a case has no BDD scenario', () => {
    const noBdd: TestCaseList = {
      ...testCases,
      test_cases: [{ ...testCases.test_cases[0]!, bdd_scenario: undefined }],
    };
    const feature = testCasesToFeature(noBdd, 'Story');
    expect(feature).toContain('Given ');
    expect(feature).toContain('When ');
    expect(feature).toContain('Then ');
  });
});

describe('Markdown exports', () => {
  it('story markdown mirrors the result sections', () => {
    const md = storyToMarkdown(analysis);
    for (const heading of [
      '# Story analysis',
      '## INVEST',
      '## Vague phrases',
      '## Acceptance criteria',
    ]) {
      expect(md).toContain(heading);
    }
  });

  it('bug markdown contains the title and core sections', () => {
    const md = bugToMarkdown(bug);
    expect(md).toContain(`# ${bug.title}`);
    expect(md).toContain('## Steps to Reproduce');
    expect(md).toContain('## Expected Result');
  });
});

describe('ZIP export file list', () => {
  it('collects all named files plus requirements.txt', () => {
    const files = automationFiles(automation);
    const names = files.map(([name]) => name);
    expect(names).toContain(automation.test_file_name);
    expect(names).toContain(automation.page_object_file_name);
    expect(names).toContain(automation.config_file_name);
  });

  it('omits empty optional files', () => {
    const files = automationFiles({
      ...automation,
      page_object_file_name: undefined,
      page_object_code: undefined,
    });
    expect(files.map(([name]) => name)).not.toContain(automation.page_object_file_name);
  });
});
