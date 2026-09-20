import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('share links', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/test_cases', (route) =>
      streamObjectFixture(route, loadFixture('test_cases'), { delayMs: 200 }),
    );
  });

  test('dialog shows size; link opens read-only; open in workspace restores', async ({
    page,
    context,
  }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/requirements/test-cases');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByTestId('test-case-card')).toHaveCount(8);

    // Share dialog with the size line.
    await page.getByRole('button', { name: 'Share' }).click();
    await expect(page.getByRole('dialog', { name: 'Share read-only result' })).toBeVisible();
    await expect(page.getByText(/Link is \d+ KB/)).toBeVisible();

    const link = await page.getByLabel('Share link').inputValue();
    expect(link).toContain('/share#');
    await page.getByRole('button', { name: 'Copy link' }).click();
    await expect(page.getByText('Link copied')).toBeVisible();

    // Open the link in a fresh page: banner, stepper, and cards render.
    const shared = await context.newPage();
    await shared.goto(link);
    await waitForApp(shared);
    await expect(shared.getByText(/Shared read-only result ·/)).toBeVisible();
    await expect(shared.getByTestId('test-case-card')).toHaveCount(8);

    // Open in my workspace restores the run (active step is story: no story output shared).
    await shared.getByRole('button', { name: 'Open in my workspace' }).click();
    await expect(shared).toHaveURL(/\/requirements\/story$/);
    const adoptedCount = await shared.evaluate(() => {
      const raw = window.sessionStorage.getItem('qag.run.current');
      const run = raw
        ? (JSON.parse(raw) as { testCases?: { output?: { test_cases?: unknown[] } } })
        : {};
      return run.testCases?.output?.test_cases?.length ?? 0;
    });
    expect(adoptedCount).toBe(8);
    await shared.goto('/requirements/test-cases');
    await expect(shared.getByTestId('test-case-card')).toHaveCount(8);
  });

  test('missing fragment renders a friendly error', async ({ page }) => {
    await page.goto('/share');
    await expect(page.getByText('Share link could not be read')).toBeVisible();
  });
});
