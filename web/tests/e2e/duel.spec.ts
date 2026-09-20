import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('ambiguity duel', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/story_analyzer', (route) =>
      streamObjectFixture(route, loadFixture('story_analyzer'), { delayMs: 200 }),
    );
    await page.route('**/api/generate/story_interpretation', (route) => {
      const body = (route.request().postDataJSON() ?? {}) as { persona?: string };
      const file = body.persona === 'B' ? 'sample-b.json' : 'sample-a.json';
      return streamObjectFixture(route, loadFixture('story_interpretation', file), {
        delayMs: 200,
      });
    });
    await page.route('**/api/generate/duel_compare', (route) =>
      streamObjectFixture(route, loadFixture('duel_compare'), { delayMs: 200 }),
    );
  });

  test('runs three calls, highlights vague phrases, and applies a rewrite', async ({ page }) => {
    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByText('acceptance-criteria-1.feature')).toBeVisible();

    await page.getByRole('button', { name: 'Run ambiguity duel' }).click();

    // Three status pills complete; the panel shows forks and highlights.
    await expect(page.getByTestId('duel-panel')).toBeVisible();
    await expect(page.getByText('3 forks')).toBeVisible();
    await expect(page.getByText('3 vague phrases')).toBeVisible();
    await expect(page.getByText(/agreement \d+%/)).toBeVisible();
    const marks = page.getByTestId('duel-mark');
    await expect(marks).toHaveCount(3);

    // Hovering a mark shows the two readings and the rewrite.
    await marks.first().hover();
    await expect(page.getByRole('tooltip').first()).toContainText('Rewrite:');

    // Apply rewrite changes the story textarea.
    await page.getByRole('button', { name: 'Apply rewrite' }).first().click();
    const storyBox = page.getByLabel('User Story / Requirement');
    await expect(storyBox).toContainText('locks after 5 consecutive failed login attempts');
    await expect(
      page.getByText('Story edited from a duel rewrite. Generate again to re-analyze.'),
    ).toBeVisible();
  });
});
