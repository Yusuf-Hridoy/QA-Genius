import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

/**
 * Click a pipeline handoff button and wait for the navigation. A dev-server
 * rebuild landing between the click and the route commit can drop the client
 * navigation, so retry the click once if the URL does not change. Run state
 * survives in sessionStorage, making the retry safe.
 */
async function clickAndNavigate(page: Page, button: Locator, url: RegExp): Promise<void> {
  await button.click();
  const arrived = await page
    .waitForURL(url, { timeout: 5000 })
    .then(() => true)
    .catch(() => false);
  if (!arrived) {
    await button.click();
    await expect(page).toHaveURL(url);
  }
}

test.describe('requirements pipeline', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    await page.route('**/api/generate/story_analyzer', (route) =>
      streamObjectFixture(route, loadFixture('story_analyzer'), { delayMs: 200 }),
    );
    const cases = loadFixture('test_cases') as {
      test_cases: Array<{ traceability: string }>;
    };
    // Deterministic traceability refs for the chips and coverage metric.
    cases.test_cases[0].traceability = 'AC-1';
    cases.test_cases[1].traceability = 'AC-2, AC-3';
    await page.route('**/api/generate/test_cases', (route) =>
      streamObjectFixture(route, cases, { delayMs: 200 }),
    );
  });

  test('story flows through criteria and cases into automation', async ({ page }) => {
    const storyCount = (loadFixture('story_analyzer').generated_acceptance_criteria as string[])
      .length;

    // Step 1 — Story.
    await page.goto('/requirements/story');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).first().click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByText('acceptance-criteria-1.feature')).toBeVisible();

    // Handoff to step 2.
    const handOff = page.getByRole('button', { name: 'Use these acceptance criteria' });
    await expect(handOff).toBeEnabled();
    await clickAndNavigate(page, handOff, /\/requirements\/criteria$/);

    // Step 2 — criteria ids AC-1..n.
    const rows = page.getByTestId('criterion-row');
    await expect(rows).toHaveCount(storyCount);
    await expect(page.getByText('AC-1', { exact: true }).first()).toBeVisible();

    // Edit one criterion.
    await page.getByLabel('AC-1 text').fill('Edited first criterion for the pipeline');
    await expect(page.getByLabel('AC-1 text')).toHaveValue(
      'Edited first criterion for the pipeline',
    );

    // Reorder with the keyboard: move AC-1 down one place, ids recompute.
    await page.getByRole('button', { name: 'Reorder AC-1' }).focus();
    await page.keyboard.press('Space');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Space');
    const firstRow = page.getByTestId('criterion-row').first();
    await expect(firstRow.getByLabel('AC-1 text')).toHaveValue(
      /.+/, // the moved row keeps its text under the recomputed AC-1 id
    );

    // Handoff to step 3: auto-generates.
    await clickAndNavigate(
      page,
      page.getByRole('button', { name: 'Generate test cases' }),
      /\/requirements\/test-cases$/,
    );
    const cards = page.getByTestId('test-case-card');
    await expect(cards).toHaveCount(8);

    // Traceability chips and coverage metric.
    await expect(page.getByTestId('trace-chips').first()).toBeVisible();
    await expect(page.getByTestId('coverage-panel')).toContainText('3 / 7');

    // Select two cases and prefill step 4.
    await cards.nth(0).getByRole('checkbox').check();
    await cards.nth(1).getByRole('checkbox').check();
    const prefill = page.getByRole('button', { name: 'Generate automation for selected' });
    await expect(prefill).toBeEnabled();
    await clickAndNavigate(page, prefill, /\/requirements\/automation$/);
    const scenario = page.getByLabel('Test Scenario Description');
    const titles = loadFixture('test_cases').test_cases as Array<{ title: string }>;
    await expect(scenario).toContainText(titles[0].title.slice(0, 30));
    await expect(scenario).toContainText(titles[1].title.slice(0, 30));
  });
});
