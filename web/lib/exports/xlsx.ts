import * as XLSX from 'xlsx-js-style';
import type { TestCase, TestCaseList } from '@/lib/generators/test-cases/schema';
import { dateStamp, downloadBlob } from './download';

const HEADERS = [
  'ID',
  'Title',
  'Category',
  'Priority',
  'Pre-conditions',
  'Steps',
  'Expected Result',
  'Test Data',
  'BDD Scenario',
  'Auto Feasibility',
  'Auto Effort',
  'Tags',
  'Traceability',
] as const;

function testCaseRow(tc: TestCase): string[] {
  return [
    tc.id,
    tc.title,
    tc.category,
    tc.priority,
    tc.pre_conditions,
    tc.steps.map((step, i) => `${i + 1}. ${step}`).join('\n'),
    tc.expected_result,
    tc.test_data ?? '',
    tc.bdd_scenario ?? '',
    tc.automation_feasibility,
    tc.automation_effort,
    tc.tags.join(', '),
    tc.traceability,
  ];
}

/**
 * XLSX workbook (port of v1 utils.export_test_cases_to_excel structure):
 * sheet "Test Cases" (bold header, frozen header, widths, wrapped long cells)
 * + sheet "Summary" (total, automation potential, category/priority breakdown,
 * coverage gaps, recommendations).
 */
export function buildTestCasesWorkbook(result: TestCaseList): XLSX.WorkBook {
  const wb = XLSX.utils.book_new();

  const headerCells = HEADERS.map((h) => ({
    v: h,
    t: 's' as const,
    s: { font: { bold: true, color: { rgb: 'FFFFFF' } }, fill: { fgColor: { rgb: '1F5E46' } } },
  }));
  const dataRows = result.test_cases.map((tc) =>
    testCaseRow(tc).map((v) => ({
      v,
      t: 's' as const,
      s: { alignment: { vertical: 'top', wrapText: true } },
    })),
  );
  const ws = XLSX.utils.aoa_to_sheet([headerCells, ...dataRows]);
  ws['!cols'] = HEADERS.map((h) => ({ wch: h === 'Title' || h === 'Expected Result' ? 40 : 18 }));
  ws['!freeze'] = {
    xSplit: 0,
    ySplit: 1,
    topLeftCell: 'A2',
    activePane: 'bottomLeft',
    state: 'frozen',
  };
  XLSX.utils.book_append_sheet(wb, ws, 'Test Cases');

  const summary = result.summary;
  const summaryRows: [string, string][] = [
    ['Total Generated', String(summary.total_generated)],
    ['Automation Coverage Potential', summary.automation_coverage_potential],
    ...summary.category_breakdown.map((c): [string, string] => [
      `Category: ${c.category}`,
      String(c.count),
    ]),
    ...summary.priority_breakdown.map((p): [string, string] => [
      `Priority: ${p.priority}`,
      String(p.count),
    ]),
  ];
  const ws2 = XLSX.utils.aoa_to_sheet([
    [
      {
        v: 'Metric',
        t: 's',
        s: { font: { bold: true, color: { rgb: 'FFFFFF' } }, fill: { fgColor: { rgb: '1F5E46' } } },
      },
      {
        v: 'Value',
        t: 's',
        s: { font: { bold: true, color: { rgb: 'FFFFFF' } }, fill: { fgColor: { rgb: '1F5E46' } } },
      },
    ],
    ...summaryRows,
    [],
    ['Coverage Gaps', ''],
    ...summary.coverage_gaps.map((g): [string] => [g]),
    [],
    ['Recommendations', ''],
    ...summary.recommendations.map((r): [string] => [r]),
  ]);
  ws2['!cols'] = [{ wch: 40 }, { wch: 60 }];
  XLSX.utils.book_append_sheet(wb, ws2, 'Summary');

  return wb;
}

export function testCasesToXlsx(result: TestCaseList): ArrayBuffer {
  return XLSX.write(buildTestCasesWorkbook(result), {
    bookType: 'xlsx',
    type: 'array',
  }) as ArrayBuffer;
}

export function downloadTestCasesXlsx(result: TestCaseList, slug: string) {
  const buffer = testCasesToXlsx(result);
  downloadBlob(
    `${slug}-test-cases-${dateStamp()}.xlsx`,
    new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
  );
}
