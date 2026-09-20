import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, type Page, type Route } from '@playwright/test';

const FIXTURES = join(__dirname, '..', '..', '..', 'fixtures');

export function loadFixture(kind: string, file = 'sample-output.json'): Record<string, unknown> {
  return JSON.parse(readFileSync(join(FIXTURES, kind, file), 'utf8')) as Record<string, unknown>;
}

/**
 * Fulfill a /api/generate/* route with the fixture as a text stream in the AI
 * SDK partial-JSON format. A small delay lets the client render its streaming
 * (skeleton) state before the first chunk arrives.
 */
export async function streamObjectFixture(
  route: Route,
  fixture: unknown,
  options: { delayMs?: number; headers?: Record<string, string> } = {},
): Promise<void> {
  const json = JSON.stringify(fixture);
  // 3–5 chunks of the serialized object.
  const chunkCount = Math.min(5, Math.max(3, Math.ceil(json.length / 1500)));
  const chunkSize = Math.ceil(json.length / chunkCount);
  const chunks = Array.from({ length: chunkCount }, (_, i) =>
    json.slice(i * chunkSize, (i + 1) * chunkSize),
  );

  if (options.delayMs) {
    await new Promise((resolve) => setTimeout(resolve, options.delayMs));
  }

  await route.fulfill({
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'x-qag-provider': 'gemini',
      'x-qag-model': 'gemini-2.5-flash-lite',
      'x-qag-tier': 'fast',
      'x-qag-request-id': 'e2e-request-1',
      'Cache-Control': 'no-store',
      ...options.headers,
    },
    body: chunks.join(''),
  });
}

/** Fulfill the ping route (key Test button). */
export async function pingFixture(route: Route): Promise<void> {
  await route.fulfill({
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'x-qag-provider': 'gemini',
      'x-qag-model': 'gemini-2.5-flash-lite',
      'x-qag-tier': 'fast',
      'x-qag-latency-ms': '42',
      'Cache-Control': 'no-store',
    },
    body: JSON.stringify({ ok: true }),
  });
}

/** JSON error response for /api/generate/* routes. */
export async function errorFixture(
  route: Route,
  status: number,
  body: Record<string, unknown>,
): Promise<void> {
  await route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    body: JSON.stringify(body),
  });
}

/** Wait for React hydration (AppShell sets data-hydrated once mounted). */
export async function waitForApp(page: Page): Promise<void> {
  await expect(page.locator("[data-hydrated='true']")).toHaveCount(1);
}

/** Seed a default Gemini key so generator screens are usable. */
export const SEED_KEY_SCRIPT = `localStorage.setItem("qag.keys.v1", JSON.stringify({
  state: {
    keys: [{ id: "e2e-key", provider: "gemini", label: "Gemini", apiKey: "e2e-test-key-123456", createdAt: new Date().toISOString() }],
    defaultKeyId: "e2e-key",
    tier: "fast"
  },
  version: 1
}));`;
