import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('bug report generation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/bug_report', (route) =>
      streamObjectFixture(route, loadFixture('bug_report'), { delayMs: 200 }),
    );
  });

  test('derived reproducibility, warning, and result render', async ({ page }) => {
    await page.goto('/bug-desk');
    await waitForApp(page);

    await page
      .getByLabel('Raw Bug Notes')
      .fill(
        'Checkout pay button stops responding after applying a coupon on staging. No spinner, no network call, cart total shows 0.00 until refresh. Reproduced in Safari.',
      );
    await page.getByLabel('Total attempts').fill('5');
    await page.getByLabel('Times reproduced').fill('2');
    await expect(page.getByText('Intermittent (2 of 5)')).toBeVisible();

    // Successful equals total → warning.
    await page.getByLabel('Times reproduced').fill('5');
    await expect(
      page.getByText(
        'Successful attempts equals total attempts — this may not be a reproducible bug.',
      ),
    ).toBeVisible();

    // Back to a valid intermittent pair, then generate.
    await page.getByLabel('Times reproduced').fill('3');
    await page.getByRole('button', { name: 'Generate' }).click();

    const fixture = loadFixture('bug_report');
    await expect(page.getByRole('heading', { name: fixture.title as string })).toBeVisible();
    for (const step of (fixture.steps_to_reproduce as string[]).slice(0, 2)) {
      await expect(page.getByText(step)).toBeVisible();
    }
  });
});
