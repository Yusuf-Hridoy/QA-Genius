import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('automation generation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/automation_script', (route) =>
      streamObjectFixture(route, loadFixture('automation_script'), { delayMs: 200 }),
    );
  });

  test('language radio hides for Python frameworks; file tree works', async ({ page }) => {
    await page.goto('/requirements');
    await waitForApp(page);
    await page.getByRole('tab', { name: 'Automation' }).click();

    await page.getByRole('radio', { name: 'Playwright (Python)' }).check();
    await expect(page.getByText('Language', { exact: true })).toBeHidden();

    await page.getByRole('radio', { name: 'Playwright (JavaScript)' }).check();
    await expect(page.getByText('Language', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();

    const fixture = loadFixture('automation_script');
    const structure = fixture.project_structure as string[];

    // File tree lists every file that carries code (downloadable files).
    const codeFiles = [
      fixture.page_object_file_name,
      fixture.test_file_name,
      fixture.config_file_name,
    ] as string[];
    for (const file of codeFiles) {
      await expect(page.getByRole('button', { name: file, exact: true })).toBeVisible();
    }
    expect(codeFiles.length).toBeGreaterThanOrEqual(2);
    expect(structure.length).toBeGreaterThanOrEqual(codeFiles.length);

    // First file is selected; clicking another changes the code header.
    await expect(page.getByText('pages/login-page.ts').last()).toBeVisible();
    await page.getByRole('button', { name: 'tests/lockout.spec.ts', exact: true }).click();
    await expect(page.getByText('tests/lockout.spec.ts').last()).toBeVisible();

    // Setup and run sections.
    await expect(page.getByRole('heading', { name: 'Setup' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Run' })).toBeVisible();
    await expect(page.getByText(fixture.execution_command as string)).toBeVisible();
  });
});
