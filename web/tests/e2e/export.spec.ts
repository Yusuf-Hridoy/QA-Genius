import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import Papa from 'papaparse';
import * as XLSX from 'xlsx-js-style';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('exports', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/test_cases', (route) =>
      streamObjectFixture(route, loadFixture('test_cases')),
    );
    await page.goto('/requirements/test-cases');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByTestId('test-case-card')).toHaveCount(8);
  });

  test('CSV downloads with a header and one row per case', async ({ page }) => {
    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'CSV' }).click(),
    ]).then(([d]) => d);
    expect(download.suggestedFilename()).toMatch(/aurora-storefront-test-cases-\d{8}\.csv/);
    const path = await download.path();
    const text = readFileSync(path as string, 'utf8');
    const parsed = Papa.parse<string[]>(text.replace(/^\uFEFF/, ''));
    expect(parsed.data[0]?.[0]).toBe('ID');
    expect(parsed.data.length).toBe(9);
  });

  test('XLSX downloads with the Test Cases sheet', async ({ page }) => {
    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'XLSX' }).click(),
    ]).then(([d]) => d);
    const path = await download.path();
    const wb = XLSX.read(readFileSync(path as string));
    expect(wb.SheetNames).toContain('Test Cases');
  });

  test('.feature downloads with one Scenario per case', async ({ page }) => {
    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: '.feature' }).click(),
    ]).then(([d]) => d);
    const path = await download.path();
    const text = readFileSync(path as string, 'utf8');
    expect(text.match(/Scenario:/g)?.length).toBe(8);
    expect(text.startsWith('Feature:')).toBe(true);
  });
});
