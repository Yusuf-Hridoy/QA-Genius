import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AutomationRequest } from '@/lib/generators/automation-script/request';
import { AutomationScript } from '@/lib/generators/automation-script/schema';
import {
  buildRepairInstructions,
  checkAndRepairOnce,
  previousFilesFor,
} from '@/lib/automation/repair';
import type { FileReport } from '@/lib/automation/syntax-check';
import type { StoredKey } from '@/lib/store/keys';

const defaultKey: StoredKey = {
  id: 'key-1',
  provider: 'gemini',
  label: 'Gemini',
  apiKey: 'test-key-value',
  createdAt: new Date().toISOString(),
};

const input = AutomationRequest.parse({
  scenario:
    'On https://staging.aurora-shop.dev/login, verify the account locks after 5 failed attempts.',
  framework: 'Playwright (JavaScript)',
  language: 'TypeScript',
});

function scriptWith(code: string): AutomationScript {
  return AutomationScript.parse({
    framework: 'Playwright (JavaScript)',
    project_structure: ['tests/a.spec.ts'],
    test_file_name: 'tests/a.spec.ts',
    test_code: code,
    setup_instructions: ['npm install'],
    execution_command: 'npx playwright test',
  });
}

const brokenScript = scriptWith(
  "test('x', async ({ page }) => {\n  await expect(page).toBeTruthy();\n});\n",
);
const fixedScript = scriptWith(
  "import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n  await expect(page).toBeTruthy();\n});\n",
);

function report(errors: Array<{ line: number; column: number; message: string }>): FileReport {
  return {
    name: 'tests/a.spec.ts',
    language: 'ts',
    errors: errors.map((e) => ({ ...e, code: 'missing-import' })),
    warnings: [],
    checked: true,
  };
}

const errorReports: FileReport[] = [
  report([
    { line: 1, column: 1, message: '“test” is used but not imported or declared.' },
    { line: 2, column: 9, message: '“expect” is used but not imported or declared.' },
  ]),
];
const cleanReports: FileReport[] = [
  { name: 'tests/a.spec.ts', language: 'ts', errors: [], warnings: [], checked: true },
];

/** A fetch mock that streams one JSON object as the repair response. */
function mockRepairResponse(payload: unknown) {
  const encoder = new TextEncoder();
  const json = JSON.stringify(payload);
  return vi.fn(async () =>
    Promise.resolve(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(json));
            controller.close();
          },
        }),
        { headers: { 'x-qag-provider': 'gemini' } },
      ),
    ),
  );
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('repair instructions', () => {
  it('lists each diagnostic as file:line:col — message', () => {
    const instructions = buildRepairInstructions(errorReports);
    expect(instructions).toContain('Fix ONLY the following syntax');
    expect(instructions).toContain(
      'tests/a.spec.ts:1:1 — “test” is used but not imported or declared.',
    );
    expect(instructions).toContain(
      'tests/a.spec.ts:2:9 — “expect” is used but not imported or declared.',
    );
  });

  it('caps previous files at 8 files of 20 000 characters', () => {
    const files = previousFilesFor(fixedScript);
    expect(files).toHaveLength(1);
    expect(files[0]?.name).toBe('tests/a.spec.ts');
    const big = scriptWith(`// ${'x'.repeat(30_000)}\n`);
    expect(previousFilesFor(big)[0]?.code.length).toBe(20_000);
  });
});

describe('checkAndRepairOnce', () => {
  it('repairs errors with exactly one request carrying instructions and previousFiles', async () => {
    fetchMock.mockImplementation(mockRepairResponse(fixedScript));
    const check = vi.fn().mockResolvedValueOnce(errorReports).mockResolvedValueOnce(cleanReports);

    const result = await checkAndRepairOnce({
      script: brokenScript,
      input,
      defaultKey,
      tier: 'reasoning',
      check,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0] as [string, { body: string }];
    const body = JSON.parse((options as { body: string }).body) as {
      instructions: string;
      previousFiles: Array<{ name: string; code: string }>;
      scenario: string;
    };
    expect(body.scenario).toBe(input.scenario);
    expect(body.instructions).toContain('tests/a.spec.ts:1:1');
    expect(body.instructions).toContain('tests/a.spec.ts:2:9');
    expect(body.previousFiles).toHaveLength(1);
    expect(body.previousFiles[0]?.name).toBe('tests/a.spec.ts');
    expect(result.repairedScript).toEqual(fixedScript);
    expect(result.badge.status).toBe('repaired');
    if (result.badge.status === 'repaired') expect(result.badge.wasErrors).toBe(2);
    expect(result.beforeErrors).toBe(2);
    expect(result.afterErrors).toBe(0);
  });

  it('makes no repair request when the output is clean', async () => {
    fetchMock.mockImplementation(mockRepairResponse(fixedScript));
    const check = vi.fn().mockResolvedValue(cleanReports);

    const result = await checkAndRepairOnce({
      script: fixedScript,
      input,
      defaultKey,
      tier: 'reasoning',
      check,
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.badge.status).toBe('clean');
    expect(result.repairedScript).toBeUndefined();
  });

  it('reports errors when the repair still fails', async () => {
    fetchMock.mockImplementation(mockRepairResponse(brokenScript));
    const check = vi.fn().mockResolvedValue(errorReports);

    const result = await checkAndRepairOnce({
      script: brokenScript,
      input,
      defaultKey,
      tier: 'reasoning',
      check,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.badge.status).toBe('errors');
    expect(result.beforeErrors).toBe(2);
    expect(result.afterErrors).toBe(2);
    expect(result.repairedScript).toEqual(brokenScript);
  });
});

describe('automation request caps', () => {
  const base = {
    scenario:
      'On https://staging.aurora-shop.dev/login, verify the account locks after 5 failed attempts.',
  };
  const file = { name: 'tests/a.spec.ts', code: 'x'.repeat(100) };

  it('accepts up to 8 files', () => {
    expect(
      AutomationRequest.parse({ ...base, previousFiles: Array.from({ length: 8 }, () => file) })
        .previousFiles,
    ).toHaveLength(8);
    expect(() =>
      AutomationRequest.parse({ ...base, previousFiles: Array.from({ length: 9 }, () => file) }),
    ).toThrow();
  });

  it('caps each file at 20 000 characters', () => {
    expect(() =>
      AutomationRequest.parse({ ...base, previousFiles: [{ ...file, code: 'x'.repeat(20_001) }] }),
    ).toThrow();
    expect(
      AutomationRequest.parse({ ...base, previousFiles: [{ ...file, code: 'x'.repeat(20_000) }] })
        .previousFiles,
    ).toHaveLength(1);
  });
});
