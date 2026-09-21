import { expect, test } from '@playwright/test';
import {
  loadFixture,
  SEED_KEY_SCRIPT,
  streamObjectFixture,
  waitForApp,
} from './helpers/stream-fixture';

const BASE = loadFixture('automation_script') as Record<string, unknown>;

/** Same project but the spec forgot its page-object import: exactly 1 error. */
function brokenFixture(): Record<string, unknown> {
  const code = BASE.test_code as string;
  return {
    ...BASE,
    test_code: code
      .split('\n')
      .filter((line) => !line.includes("from '../pages/login-page'"))
      .join('\n'),
  };
}

/** Fixed project with one remaining hardcoded sleep (a warning row to click). */
function fixedWithWarningFixture(): Record<string, unknown> {
  const code = BASE.test_code as string;
  return {
    ...BASE,
    test_code: code.replace(
      'await login.expectLocked();',
      'await page.waitForTimeout(1000);\n    await login.expectLocked();',
    ),
  };
}

/** Python project: nothing is syntax-checked in this phase. */
function pythonFixture(): Record<string, unknown> {
  return {
    ...BASE,
    framework: 'Playwright (Python)',
    page_object_file_name: 'pages/login_page.py',
    page_object_code: 'class LoginPage:\n    pass\n',
    test_file_name: 'tests/test_login.py',
    test_code: 'def test_login(page):\n    assert True\n',
    conftest_file_name: 'conftest.py',
    conftest_code: 'import pytest\n',
    config_file_name: undefined,
    config_code: undefined,
  };
}

test.describe('automation syntax check', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(SEED_KEY_SCRIPT);
  });

  test('broken output triggers one repair and shows the repaired badge', async ({ page }) => {
    const bodies: unknown[] = [];
    await page.route('**/api/generate/automation_script', async (route) => {
      try {
        bodies.push(route.request().postDataJSON());
      } catch {
        bodies.push(null);
      }
      await streamObjectFixture(
        route,
        bodies.length === 1 ? brokenFixture() : fixedWithWarningFixture(),
      );
    });

    await page.goto('/requirements/automation');
    await waitForApp(page);

    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();

    // One repair attempt: the second request carries previousFiles + instructions.
    await expect(page.getByTestId('automation-syntax-badge')).toContainText(
      'repaired · was 1 error',
      { timeout: 60_000 },
    );
    expect(bodies).toHaveLength(2);
    const second = bodies[1] as {
      previousFiles?: Array<{ name: string; code: string }>;
      instructions?: string;
    };
    const specFile = second.previousFiles?.find((f) => f.name === 'tests/lockout.spec.ts');
    expect(specFile?.code).toContain('LoginPage');
    expect(second.previousFiles).toHaveLength(3);
    expect(second.instructions).toContain('tests/lockout.spec.ts:');
    expect(second.instructions).toContain('Fix ONLY the following syntax');

    // Diagnostics panel shows the before → after counts with a warning row.
    const panel = page.getByTestId('automation-diagnostics');
    await expect(panel).toContainText('1 → 0 errors');
    await expect(panel.getByRole('button', { name: /Hardcoded sleep/ })).toBeVisible();

    // Clicking the row highlights the line in the code viewer.
    await panel.getByRole('button', { name: /Hardcoded sleep/ }).click();
    const highlighted = page.locator('.qag-highlight-line');
    await expect(highlighted.first()).toBeVisible();
    await expect(highlighted.first()).toContainText('waitForTimeout');
  });

  test('clean output shows syntax clean with no repair request', async ({ page }) => {
    const bodies: unknown[] = [];
    await page.route('**/api/generate/automation_script', async (route) => {
      try {
        bodies.push(route.request().postDataJSON());
      } catch {
        bodies.push(null);
      }
      await streamObjectFixture(route, BASE);
    });

    await page.goto('/requirements/automation');
    await waitForApp(page);

    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('button', { name: 'Generate' }).click();

    await expect(page.getByTestId('automation-syntax-badge')).toContainText('syntax clean', {
      timeout: 60_000,
    });
    expect(bodies).toHaveLength(1);
  });

  test('Python output shows not checked with no repair request', async ({ page }) => {
    const bodies: unknown[] = [];
    await page.route('**/api/generate/automation_script', async (route) => {
      try {
        bodies.push(route.request().postDataJSON());
      } catch {
        bodies.push(null);
      }
      await streamObjectFixture(route, pythonFixture());
    });

    await page.goto('/requirements/automation');
    await waitForApp(page);

    await page.getByRole('button', { name: 'Load example' }).click();
    await page.getByRole('radio', { name: 'Playwright (Python)' }).check();
    await page.getByRole('button', { name: 'Generate' }).click();

    await expect(page.getByTestId('automation-syntax-badge')).toContainText(
      'not checked · Python',
      { timeout: 60_000 },
    );
    expect(bodies).toHaveLength(1);
  });
});
