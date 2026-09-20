import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import Papa from 'papaparse';
import * as XLSX from 'xlsx-js-style';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

async function generateCases(page: Page): Promise<void> {
  await page.goto('/requirements/test-cases');
  await waitForApp(page);
  await page.getByRole('button', { name: 'Load example' }).click();
  await page.getByRole('button', { name: 'Generate' }).click();
  await expect(page.getByTestId('test-case-card')).toHaveCount(8);
}

test.describe('existing suite gaps', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/test_cases', (route) =>
      streamObjectFixture(route, loadFixture('test_cases'), { delayMs: 200 }),
    );
  });

  test('CSV upload guesses mapping; chips, gaps filter, and gaps CSV export work', async ({
    page,
  }) => {
    await generateCases(page);

    await page.getByRole('button', { name: 'Compare with your suite' }).click();
    await page.setInputFiles('#suite-file', 'fixtures/suite/aurora-suite.csv');
    await expect(page.getByLabel('Title column')).toHaveValue('Title');
    await expect(page.getByLabel('Steps column')).toHaveValue('Steps');
    await expect(page.getByLabel('Expected column')).toHaveValue('Expected Result');
    await page.getByRole('button', { name: 'Import suite' }).click();

    // Metric card and per-card chips.
    await expect(page.getByTestId('suite-panel')).toContainText('aurora-suite.csv');
    await expect(page.getByTestId('suite-chip')).toHaveCount(8);
    const panel = page.getByTestId('suite-panel');
    await expect(panel.getByText('6', { exact: true }).first()).toBeVisible();

    // Gaps-only filter leaves the two new cases.
    await page.getByRole('button', { name: 'Gaps only' }).click();
    await expect(page.getByTestId('test-case-card')).toHaveCount(2);

    // Export gaps CSV has only the gap rows.
    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export gaps CSV' }).click(),
    ]).then(([d]) => d);
    expect(download.suggestedFilename()).toMatch(/aurora-storefront-gaps-test-cases-\d{8}\.csv/);
    const path = await download.path();
    const parsed = Papa.parse<string[]>(
      readFileSync(path as string, 'utf8').replace(/^\uFEFF/, ''),
    );
    const rows = (parsed.data as string[][]).filter((r) => r.length > 1);
    expect(rows[0]?.[0]).toBe('ID');
    expect(rows.length).toBe(3);
    expect(rows.map((r) => r[0]).sort()).toEqual(['ID', 'TC-007', 'TC-008']);
  });

  test('XLSX upload replaces the suite and gaps XLSX exports only gaps', async ({ page }) => {
    await generateCases(page);

    await page.getByRole('button', { name: 'Compare with your suite' }).click();
    await page.setInputFiles('#suite-file', 'fixtures/suite/aurora-suite.xlsx');
    await expect(page.getByLabel('Title column')).toHaveValue('summary');
    await expect(page.getByLabel('Steps column')).toHaveValue('procedure');
    await expect(page.getByLabel('Expected column')).toHaveValue('expected result');
    await page.getByRole('button', { name: 'Import suite' }).click();

    await expect(page.getByTestId('suite-chip')).toHaveCount(8);

    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export gaps XLSX' }).click(),
    ]).then(([d]) => d);
    const path = await download.path();
    const workbook = XLSX.read(readFileSync(path as string));
    expect(workbook.SheetNames).toContain('Test Cases');
    const sheet = workbook.Sheets['Test Cases'];
    const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1 });
    expect(rows.length).toBe(3);
  });
});
