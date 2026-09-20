import { expect, test } from '@playwright/test';

/**
 * Live smoke — opt-in only. Requires LIVE_PROVIDER and LIVE_KEY env vars;
 * excluded from CI and from the default `pnpm e2e` (tests/e2e only).
 * Run with: LIVE_PROVIDER=gemini LIVE_KEY=... pnpm exec playwright test tests/live
 */
const PROVIDER = process.env.LIVE_PROVIDER;
const KEY = process.env.LIVE_KEY;

test.skip(!PROVIDER || !KEY, 'Set LIVE_PROVIDER and LIVE_KEY to run live tests');

test.describe('live smoke @live', () => {
  test('test cases generation returns cases from the real provider', async ({ page }) => {
    await page.addInitScript(
      ([provider, key]) => {
        localStorage.setItem(
          'qag.keys.v1',
          JSON.stringify({
            state: {
              keys: [
                {
                  id: 'live-key',
                  provider,
                  label: 'Live',
                  apiKey: key,
                  createdAt: new Date().toISOString(),
                },
              ],
              defaultKeyId: 'live-key',
              tier: 'fast',
            },
            version: 1,
          }),
        );
      },
      [PROVIDER as string, KEY as string],
    );

    await page.goto('/requirements');
    await page.getByRole('tab', { name: 'Test cases' }).click();
    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();

    await expect(page.getByTestId('test-case-card').first()).toBeVisible({ timeout: 120_000 });
    expect(await page.getByTestId('test-case-card').count()).toBeGreaterThanOrEqual(3);
  });
});
