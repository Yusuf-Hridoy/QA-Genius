import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

function revisedFixture(): Record<string, unknown> {
  const base = loadFixture('test_cases') as {
    test_cases: Array<{ id: string; title: string }>;
  };
  const clone = JSON.parse(JSON.stringify(base)) as typeof base;
  clone.test_cases[0].title = `REVISED ${clone.test_cases[0].title}`;
  clone.test_cases = clone.test_cases.filter((tc) => tc.id !== 'TC-008');
  const template = clone.test_cases[0];
  clone.test_cases.push(
    { ...template, id: 'TC-009', title: 'Added revision case one' },
    { ...template, id: 'TC-010', title: 'Added revision case two' },
  );
  return clone as unknown as Record<string, unknown>;
}

test.describe('refine loop', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
    let calls = 0;
    await page.route('**/api/generate/test_cases', (route) => {
      calls += 1;
      const fixture = calls === 2 ? revisedFixture() : loadFixture('test_cases');
      return streamObjectFixture(route, fixture, { delayMs: 200 });
    });
  });

  test('revision shows a diff; accept, keep, and undo work', async ({ page }) => {
    await page.goto('/requirements/test-cases');
    await waitForApp(page);
    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();
    const cards = page.getByTestId('test-case-card');
    await expect(cards).toHaveCount(8);

    // Refine with instructions.
    await page.getByRole('button', { name: 'Refine' }).click();
    await page.getByLabel('Refine test cases').fill('Make the negative cases stricter');
    await page.getByRole('button', { name: 'Generate revision' }).click();

    // Summary pills: +2 added, ~1 changed, −1 removed, 6 unchanged.
    const diff = page.getByTestId('test-cases-diff');
    await expect(diff.getByText('+2 added')).toBeVisible();
    await expect(diff.getByText('~1 changed')).toBeVisible();
    await expect(diff.getByText('−1 removed')).toBeVisible();
    await expect(diff.getByText('6 unchanged')).toBeVisible();

    // Changes-only filter hides the unchanged entries.
    await page.getByText('Show only changes').click();
    await expect(page.locator('[data-testid="diff-unchanged"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="diff-added"]')).toHaveCount(2);

    // Accept: cards update to the revision.
    await page.getByRole('button', { name: 'Accept revision' }).click();
    await expect(cards).toHaveCount(9);
    await expect(page.getByText('Added revision case one')).toBeVisible();

    // Second revision, then Keep current leaves the revision in place.
    await page.getByRole('button', { name: 'Refine' }).click();
    await page.getByLabel('Refine test cases').fill('Another pass');
    await page.getByRole('button', { name: 'Generate revision' }).click();
    await expect(page.getByTestId('test-cases-diff')).toBeVisible();
    await page.getByRole('button', { name: 'Keep current' }).click();
    await expect(cards).toHaveCount(9);

    // Third revision, then Undo restores the pre-accept version.
    await page.getByRole('button', { name: 'Refine' }).click();
    await page.getByLabel('Refine test cases').fill('Third pass');
    await page.getByRole('button', { name: 'Generate revision' }).click();
    await page.getByRole('button', { name: 'Undo last accept' }).click();
    await expect(cards).toHaveCount(8);
    await expect(page.getByText('Added revision case one')).toBeHidden();
  });
});
