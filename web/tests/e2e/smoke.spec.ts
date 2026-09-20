import { expect, test } from '@playwright/test';
import { waitForApp } from './helpers/stream-fixture';

const PAGES = [
  { path: '/requirements', heading: 'Requirements' },
  { path: '/bug-desk', heading: 'Bug desk' },
  { path: '/quality-insights', heading: 'Quality insights' },
  { path: '/non-functional', heading: 'Non-functional' },
  { path: '/settings/keys', heading: 'Settings' },
];

test.describe('smoke', () => {
  for (const { path, heading } of PAGES) {
    test(`${path} renders with exactly one h1`, async ({ page }) => {
      await page.goto(path);
      await waitForApp(page);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    });
  }

  test('sidebar lists the four workspaces', async ({ page }) => {
    await page.goto('/requirements');
    await waitForApp(page);
    const nav = page.getByRole('navigation', { name: 'Workspaces' });
    for (const label of ['Requirements', 'Bug desk', 'Quality insights', 'Non-functional']) {
      await expect(nav.getByRole('link', { name: label })).toBeVisible();
    }
  });

  test('later-phase pages show their empty states', async ({ page }) => {
    await page.goto('/quality-insights');
    await waitForApp(page);
    await expect(page.getByText('Quality insights arrives in a later phase')).toBeVisible();
    await page.goto('/non-functional');
    await waitForApp(page);
    await expect(page.getByText('Non-functional testing arrives in a later phase')).toBeVisible();
  });

  test('no console errors on any page', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    for (const { path } of PAGES) {
      await page.goto(path);
      await waitForApp(page);
      await page.waitForLoadState('networkidle');
    }
    expect(errors).toEqual([]);
  });
});
