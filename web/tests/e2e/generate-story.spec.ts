import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('story analyzer generation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/story_analyzer', (route) =>
      streamObjectFixture(route, loadFixture('story_analyzer'), { delayMs: 200 }),
    );
  });

  test('renders INVEST, acceptance criteria, and copy', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/requirements/story');
    await waitForApp(page);

    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();

    // INVEST table with six dimension rows.
    const invest = page.getByRole('table');
    for (const label of [
      'Independent',
      'Negotiable',
      'Valuable',
      'Estimable',
      'Small',
      'Testable',
    ]) {
      await expect(invest.getByRole('rowheader', { name: label })).toBeVisible();
    }

    // Acceptance criteria gherkin block.
    await expect(page.getByText('acceptance-criteria-1.feature')).toBeVisible();

    // Copy a rewrite to the clipboard.
    await page.getByRole('button', { name: 'Copy rewrite' }).first().click();
    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(
      (loadFixture('story_analyzer').suggested_rewrites as string[]).some((r) =>
        clipboard.includes(r.slice(0, 30)),
      ),
    ).toBe(true);
  });
});
