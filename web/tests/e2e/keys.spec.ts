import { expect, test } from '@playwright/test';
import { pingFixture, waitForApp } from './helpers/stream-fixture';

test.describe('key manager', () => {
  test('add, test, persist, and delete a key', async ({ page }) => {
    await page.route('**/api/generate/ping', pingFixture);

    await page.goto('/settings/keys');
    await waitForApp(page);

    // Add a Groq key (second in the provider select).
    await page.getByLabel('Provider').selectOption('groq');
    await expect(page.getByRole('link', { name: 'Get a free key' })).toBeVisible();
    await page.getByLabel('API key').fill('gsk-e2e-test-key-123456789');
    await page.getByRole('button', { name: 'Save key' }).click();
    await expect(page.getByText('Key saved')).toBeVisible();

    // Sidebar badge turns ok with the provider name.
    await expect(page.getByText('Groq · your key · never stored')).toBeVisible();

    // Reload: key persists, masked.
    await page.reload();
    await expect(page.getByText('gsk-…6789')).toBeVisible();

    // Test the key against the mocked ping route.
    await page.getByRole('button', { name: 'Test' }).click();
    await expect(page.getByText('OK · 42 ms · gemini-2.5-flash-lite').first()).toBeVisible();

    // Delete with confirmation.
    await page.getByRole('button', { name: 'Delete Groq key' }).click();
    await page
      .getByRole('dialog', { name: 'Delete key' })
      .getByRole('button', { name: 'Delete' })
      .click();
    await expect(page.getByText('Key deleted')).toBeVisible();
    await expect(page.getByText('No key — add one')).toBeVisible();
  });

  test('base URL field only appears for OpenAI-compatible', async ({ page }) => {
    await page.goto('/settings/keys');
    await waitForApp(page);
    await expect(page.getByLabel('Base URL')).toBeHidden();
    await page.getByLabel('Provider').selectOption('openai-compatible');
    await expect(page.getByLabel('Base URL')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Get a free key' })).toBeHidden();
  });
});
