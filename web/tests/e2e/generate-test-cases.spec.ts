import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('test cases generation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/test_cases', (route) =>
      streamObjectFixture(route, loadFixture('test_cases'), { delayMs: 400 }),
    );
  });

  test('generates, filters, and shows the footer', async ({ page }) => {
    await page.goto('/requirements');
    await waitForApp(page);
    await page.getByRole('tab', { name: 'Test cases' }).click();

    // Idle empty state.
    await expect(page.getByText('Generate test cases')).toBeVisible();

    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();

    // Streaming state: the Stop button replaces Generate.
    await expect(page.getByRole('button', { name: 'Stop generating' })).toBeVisible();

    // Done: one card per fixture case (>= 8).
    const cards = page.getByTestId('test-case-card');
    await expect(cards).toHaveCount(8);
    await expect(page.getByRole('button', { name: 'Stop generating' })).toBeHidden();

    // Footer shows provider, model, tier.
    await expect(page.getByText(/gemini-2\.5-flash-lite · fast · .* request e2e-…/)).toBeVisible();

    // Category filter reduces the visible set.
    await page.getByRole('button', { name: 'Negative' }).click();
    const negativeCount = (loadFixture('test_cases').test_cases as { category: string }[]).filter(
      (tc) => tc.category === 'Negative',
    ).length;
    await expect(cards).toHaveCount(negativeCount);

    // Clear restores all.
    await page.getByRole('button', { name: 'Clear' }).click();
    await expect(cards).toHaveCount(8);
  });
});
