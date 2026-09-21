import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

const TINY_PNG =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

function harText(): string {
  return JSON.stringify({
    log: {
      entries: [
        {
          request: { method: 'GET', url: 'https://staging.aurora-shop.dev/cart' },
          response: { status: 200 },
          time: 42,
        },
        {
          request: { method: 'POST', url: 'https://staging.aurora-shop.dev/api/checkout' },
          response: { status: 502 },
          time: 812,
        },
      ],
    },
  });
}

async function dropFiles(
  page: import('@playwright/test').Page,
  files: Array<{ name: string; type: string; content: string; binary?: boolean }>,
): Promise<void> {
  await page.evaluate((payload) => {
    const dt = new DataTransfer();
    for (const item of payload) {
      const bytes = item.binary
        ? Uint8Array.from(atob(item.content), (c) => c.charCodeAt(0))
        : new TextEncoder().encode(item.content);
      dt.items.add(new File([bytes], item.name, { type: item.type }));
    }
    const zone = document.querySelector('[data-testid="bug-attachments-dropzone"]');
    zone?.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true }));
  }, files);
}

const GROQ_KEY_SCRIPT = `localStorage.setItem("qag.keys.v1", JSON.stringify({
  state: {
    keys: [{ id: "e2e-groq", provider: "groq", label: "Groq", apiKey: "e2e-test-key-123456", createdAt: new Date().toISOString() }],
    defaultKeyId: "e2e-groq",
    tier: "fast"
  },
  version: 1
}));`;

test.describe('bug attachments', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
  });

  test('screenshot and HAR attach, travel in the request, and render evidence', async ({
    page,
  }) => {
    const bodies: unknown[] = [];
    await page.route('**/api/generate/bug_report', async (route) => {
      try {
        bodies.push(route.request().postDataJSON());
      } catch {
        bodies.push(null);
      }
      await streamObjectFixture(route, loadFixture('bug_report'));
    });

    await page.goto('/bug-desk');
    await waitForApp(page);

    await dropFiles(page, [
      { name: 'shot.png', type: 'image/png', content: TINY_PNG, binary: true },
    ]);
    const preview = page.getByTestId('bug-image-preview');
    await expect(preview).toBeVisible({ timeout: 15_000 });
    await expect(preview).toContainText('KB');

    await dropFiles(page, [{ name: 'network.har', type: 'application/json', content: harText() }]);
    const logPreview = page.getByTestId('bug-log-preview');
    await expect(logPreview).toBeVisible();
    await expect(logPreview).toContainText('chars kept');

    await page
      .getByLabel('Raw Bug Notes')
      .fill(
        'Checkout pay button stops responding after applying a coupon on staging. No spinner, no network call, cart total shows 0.00 until refresh. Reproduced in Safari.',
      );
    await page.getByRole('button', { name: 'Generate' }).click();

    const fixture = loadFixture('bug_report');
    await expect(page.getByRole('heading', { name: fixture.title as string })).toBeVisible({
      timeout: 30_000,
    });

    expect(bodies).toHaveLength(1);
    const body = bodies[0] as {
      attachments?: {
        image?: { mime: string; dataBase64: string };
        log?: { name: string; kind: string; text: string };
      };
    };
    expect(body.attachments?.image?.mime).toBe('image/jpeg');
    expect(body.attachments?.image?.dataBase64.length).toBeGreaterThan(100);
    expect(body.attachments?.log?.kind).toBe('har');
    expect(body.attachments?.log?.text).toContain('→ 502');

    const evidence = page.getByTestId('bug-evidence');
    await expect(evidence).toBeVisible();
    for (const note of (fixture.screenshot_annotations as string[]).slice(0, 2)) {
      await expect(evidence.getByText(note)).toBeVisible();
    }
    await expect(page.getByTestId('bug-evidence-log')).toContainText('network.har');
  });

  test('providers without vision block the screenshot drop zone', async ({ page }) => {
    await page.addInitScript(GROQ_KEY_SCRIPT);
    await page.goto('/bug-desk');
    await waitForApp(page);

    await expect(page.getByTestId('bug-vision-warning')).toContainText("can't read images");
    await dropFiles(page, [
      { name: 'shot.png', type: 'image/png', content: TINY_PNG, binary: true },
    ]);
    await expect(page.getByTestId('bug-image-preview')).toHaveCount(0);
    await expect(page.getByRole('alert')).toContainText("can't read images");
  });
});
