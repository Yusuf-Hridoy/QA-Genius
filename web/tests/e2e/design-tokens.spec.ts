import { expect, test } from '@playwright/test';
import { waitForApp } from './helpers/stream-fixture';

/**
 * Design-token guard (Phase 2.1): the look D tokens must resolve to their
 * values. Catches a shadcn variable collision that would render the app as
 * an unstyled wireframe. No API mocking needed — this asserts static styles.
 */
test.describe('design tokens', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/requirements/story');
    await waitForApp(page);
  });

  test('primary button keeps the forest-green accent', async ({ page }) => {
    const generate = page.getByRole('button', { name: 'Generate' });
    const background = await generate.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(background).toBe('rgb(31, 94, 70)');
  });

  test('cards have a visible border and a non-transparent background', async ({ page }) => {
    // A bordered card surface (the source picker pill carries both classes).
    const card = page.locator('.bg-card.border').first();
    const style = await card.evaluate((el) => {
      const computed = getComputedStyle(el);
      return {
        borderTopWidth: computed.borderTopWidth,
        backgroundColor: computed.backgroundColor,
      };
    });
    expect(style.borderTopWidth).toBe('1px');
    expect(style.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
  });

  test('muted captions render in grey, not a surface colour', async ({ page }) => {
    const caption = page.locator('.text-muted').first();
    const color = await caption.evaluate((el) => getComputedStyle(el).color);
    expect(color).toBe('rgb(133, 140, 133)');
  });

  test('keyboard focus yields a visible focus ring', async ({ page }) => {
    // Tab from the address bar lands on the skip link with keyboard modality.
    await page.keyboard.press('Tab');
    const boxShadow = await page.locator(':focus').evaluate((el) => getComputedStyle(el).boxShadow);
    expect(boxShadow).not.toBe('none');
  });
});
