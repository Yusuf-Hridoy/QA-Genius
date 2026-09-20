import { expect, test } from '@playwright/test';
import {
  errorFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

test.describe('error states', () => {
  test('generate without a key shows a toast with an Open settings action', async ({ page }) => {
    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();
    const toast = page.getByText('Add an API key to generate.');
    await expect(toast).toBeVisible();
    await page.getByRole('button', { name: 'Open settings' }).click();
    await expect(page).toHaveURL(/\/settings\/keys$/);
  });

  test('provider rate limit mentions the retry delay', async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/story_analyzer', (route) =>
      errorFixture(route, 429, {
        error: 'provider_rate_limited',
        message: 'Your provider rate-limited this key. Try again in a moment.',
        details: { retryAfter: 30 },
      }),
    );
    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(
      page.getByText(
        'Your provider rate-limited this key. Try again in a moment. Try again in 30s.',
      ),
    ).toBeVisible();
  });

  test('bad model output keeps the previous result on screen', async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    let calls = 0;
    await page.route('**/api/generate/story_analyzer', (route) => {
      calls += 1;
      if (calls === 1) {
        return streamObjectFixture(route, {
          ambiguity_score: 12,
          clarity_label: 'Crystal Clear',
          invest_overall: 'PASS',
          invest_independent: 'PASS',
          invest_negotiable: 'PASS',
          invest_valuable: 'PASS',
          invest_estimable: 'PASS',
          invest_small: 'PASS',
          invest_testable: 'PASS',
          vague_phrases: [],
          missing_elements: [],
          suggested_rewrites: [],
          generated_acceptance_criteria: [],
          risks: [],
        });
      }
      return errorFixture(route, 502, {
        error: 'bad_model_output',
        message: "The model returned output that couldn't be read. Try again or switch tier.",
      });
    });

    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByText('Ambiguity 12/100')).toBeVisible();

    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(
      page
        .getByText("The model returned output that couldn't be read. Try again or switch tier.")
        .first(),
    ).toBeVisible();
    // The previous result stays rendered.
    await expect(page.getByText('Ambiguity 12/100')).toBeVisible();
  });

  test('client-side validation shows inline field errors', async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByLabel('User Story / Requirement').fill('too short');
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByRole('alert').first()).toBeVisible();
  });
});
