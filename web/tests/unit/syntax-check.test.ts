import { describe, expect, it } from 'vitest';
import {
  checkFiles,
  countErrors,
  countWarnings,
  handleCheckRequest,
  summarizeReports,
} from '@/lib/automation/syntax-check';

const VALID_SPEC = `import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/login-page';

test('locks the account after five failures', async ({ page }) => {
  const login = new LoginPage(page);
  await login.navigate();
  await expect(page).toHaveTitle(/Aurora/);
});
`;

const PAGE_OBJECT = `import type { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly username: Locator;
  constructor(private page: Page) {
    this.username = page.getByTestId('username');
  }
  async navigate(): Promise<void> {
    await this.page.goto('/login');
  }
}
`;

describe('syntax check', () => {
  it('marks a valid project clean', async () => {
    const reports = await checkFiles([
      { name: 'pages/login-page.ts', code: PAGE_OBJECT },
      { name: 'tests/lockout.spec.ts', code: VALID_SPEC },
    ]);
    expect(reports).toHaveLength(2);
    expect(reports.every((r) => r.checked)).toBe(true);
    expect(countErrors(reports)).toBe(0);
    expect(summarizeReports(reports)).toBe('clean');
  });

  it('reports an unclosed brace with line and column', async () => {
    const reports = await checkFiles([
      {
        name: 'tests/broken.spec.ts',
        code: `import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n  await expect(page).toBeTruthy();\n`,
      },
    ]);
    expect(reports[0]?.checked).toBe(true);
    expect(reports[0]?.errors.length).toBeGreaterThan(0);
    const first = reports[0]?.errors[0];
    expect(first?.line).toBeGreaterThanOrEqual(2);
    expect(first?.column).toBeGreaterThanOrEqual(1);
    expect(summarizeReports(reports)).toBe('errors');
  });

  it('reports statements on one line without a separator as a syntax error', async () => {
    const reports = await checkFiles([
      {
        name: 'tests/oneline.spec.ts',
        code: `import { test, expect } from '@playwright/test';\ntest('x', async () => { const x = 5 const y = 6; await expect(x).toBe(5); });\n`,
      },
    ]);
    expect(countErrors(reports)).toBeGreaterThan(0);
  });

  it('flags test/expect used without an import', async () => {
    const reports = await checkFiles([
      {
        name: 'tests/noimport.spec.ts',
        code: `test('x', async ({ page }) => {\n  await expect(page).toBeTruthy();\n});\n`,
      },
    ]);
    const messages = (reports[0]?.errors ?? []).map((e) => e.message);
    expect(messages.some((m) => m.includes('“test”'))).toBe(true);
    expect(messages.some((m) => m.includes('“expect”'))).toBe(true);
    expect(reports[0]?.errors.every((e) => e.code === 'missing-import')).toBe(true);
  });

  it('exempts Cypress globals when the framework is Cypress', async () => {
    const code = `describe('cart', () => {\n  it('adds an item', () => {\n    cy.visit('/cart');\n  });\n});\n`;
    const cypress = await checkFiles([{ name: 'cypress/e2e/cart.cy.js', code }], {
      framework: 'Cypress (JavaScript)',
    });
    expect(cypress[0]?.errors).toHaveLength(0);
    const playwright = await checkFiles([{ name: 'tests/cart.spec.ts', code }]);
    expect(playwright[0]?.errors.length).toBeGreaterThan(0);
  });

  it('flags a page object used without an import', async () => {
    const spec = `import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n  const login = new LoginPage(page);\n  await expect(login).toBeTruthy();\n});\n`;
    const reports = await checkFiles([
      { name: 'pages/login-page.ts', code: PAGE_OBJECT },
      { name: 'tests/uses-page.spec.ts', code: spec },
    ]);
    const specReport = reports.find((r) => r.name === 'tests/uses-page.spec.ts');
    expect(
      specReport?.errors.some(
        (e) => e.code === 'page-object-not-imported' && e.message.includes('LoginPage'),
      ),
    ).toBe(true);
  });

  it('flags an empty test body', async () => {
    const reports = await checkFiles([
      {
        name: 'tests/empty.spec.ts',
        code: `import { test } from '@playwright/test';\ntest('does nothing', async () => {});\n`,
      },
    ]);
    expect(reports[0]?.errors.some((e) => e.code === 'empty-test-body')).toBe(true);
  });

  it('treats hardcoded sleeps as warnings, never errors', async () => {
    const reports = await checkFiles([
      {
        name: 'tests/sleepy.spec.ts',
        code: `import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n  await page.waitForTimeout(2000);\n  await expect(page).toBeTruthy();\n});\n`,
      },
    ]);
    expect(reports[0]?.errors).toHaveLength(0);
    expect(reports[0]?.warnings.some((w) => w.code === 'hardcoded-sleep')).toBe(true);
    expect(countWarnings(reports)).toBe(1);
    expect(summarizeReports(reports)).toBe('clean');
  });

  it('marks Python files as not checked', async () => {
    const reports = await checkFiles([
      { name: 'tests/test_login.py', code: 'def test_login(page):\n    assert True\n' },
    ]);
    expect(reports[0]).toMatchObject({ language: 'python', checked: false });
    expect(summarizeReports(reports)).toBe('unchecked');
  });

  it('marks config and docs as not checked but keeps them in the report', async () => {
    const reports = await checkFiles([
      {
        name: 'playwright.config.ts',
        code: `import { defineConfig } from '@playwright/test';\nexport default defineConfig({});\n`,
      },
      { name: 'README.md', code: '# project\n' },
    ]);
    expect(reports.find((r) => r.name === 'playwright.config.ts')?.checked).toBe(true);
    expect(reports.find((r) => r.name === 'README.md')).toMatchObject({
      language: 'other',
      checked: false,
    });
  });

  it('summarizes mixed statuses', async () => {
    const clean = await checkFiles([{ name: 'tests/a.spec.ts', code: VALID_SPEC }]);
    expect(summarizeReports(clean)).toBe('clean');
    const broken = await checkFiles([
      { name: 'tests/a.spec.ts', code: VALID_SPEC },
      { name: 'tests/b.spec.ts', code: 'test(' },
    ]);
    expect(summarizeReports(broken)).toBe('errors');
    const onlyPython = await checkFiles([{ name: 't.py', code: 'x = 1\n' }]);
    expect(summarizeReports(onlyPython)).toBe('unchecked');
  });
});

describe('worker message protocol', () => {
  it('maps a request to a response with the same id', async () => {
    const response = await handleCheckRequest({
      id: 7,
      files: [{ name: 'tests/a.spec.ts', code: VALID_SPEC }],
      framework: 'Playwright (JavaScript)',
    });
    expect(response.id).toBe(7);
    expect(response.reports).toHaveLength(1);
    expect(response.reports[0]?.name).toBe('tests/a.spec.ts');
  });
});
