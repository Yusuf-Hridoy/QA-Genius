'use client';

import { generateOne } from '@/lib/client/generate-one';
import { buildByokHeaders } from '@/lib/llm/byok';
import type { StoredKey } from '@/lib/store/keys';
import type { Tier } from '@/lib/llm/providers';
import { AutomationRequest } from '@/lib/generators/automation-script/request';
import { AutomationScript } from '@/lib/generators/automation-script/schema';
import { automationFiles } from '@/lib/exports/zip';
import { checkFiles, countErrors, countWarnings, summarizeReports } from './syntax-check';
import type { FileReport, InputFile } from './syntax-check';
import type { SyntaxBadge } from './syntax-store';

export const MAX_REPAIR_FILES = 8;
export const MAX_REPAIR_FILE_CHARS = 20_000;

const REPAIR_LEAD =
  'Fix ONLY the following syntax and structural problems in the previously generated files. ' +
  'Return the complete corrected project with the same file names. ' +
  'Do not change behaviour or add features.';

/** Fix-only instructions listing each diagnostic as file:line:col — message. */
export function buildRepairInstructions(reports: FileReport[]): string {
  const lines = [REPAIR_LEAD];
  for (const report of reports) {
    for (const error of report.errors) {
      lines.push(`${report.name}:${error.line}:${error.column} — ${error.message}`);
    }
  }
  return lines.join('\n');
}

/**
 * The previously generated files for the repair request: same file names,
 * capped at 8 files of 20 000 characters (the request schema caps).
 */
export function previousFilesFor(script: AutomationScript): Array<{ name: string; code: string }> {
  return automationFiles(script)
    .slice(0, MAX_REPAIR_FILES)
    .map(([name, code]) => ({ name, code: code.slice(0, MAX_REPAIR_FILE_CHARS) }));
}

export type RepairOutcome =
  { repaired: true; script: AutomationScript } | { repaired: false; reason: string };

/**
 * Exactly one repair attempt: same request plus fix-only instructions and the
 * previously generated files. Returns the corrected project when it parses.
 */
export async function requestRepair(args: {
  input: AutomationRequest;
  script: AutomationScript;
  reports: FileReport[];
  defaultKey: StoredKey;
  tier: Tier;
}): Promise<RepairOutcome> {
  const body = {
    ...args.input,
    instructions: buildRepairInstructions(args.reports),
    previousFiles: previousFilesFor(args.script),
  };
  let data: unknown;
  try {
    const result = await generateOne(
      'automation_script',
      body,
      buildByokHeaders(args.defaultKey, args.tier),
    );
    data = result.data;
  } catch (error) {
    return {
      repaired: false,
      reason: error instanceof Error ? error.message : 'The repair request failed.',
    };
  }
  const parsed = AutomationScript.safeParse(data);
  if (!parsed.success) {
    return { repaired: false, reason: 'The repair returned output that could not be read.' };
  }
  return { repaired: true, script: parsed.data };
}

export type CheckRepairResult = {
  badge: SyntaxBadge;
  beforeErrors: number;
  afterErrors: number;
  warnings: number;
  reports: FileReport[];
  /** Present when a repair attempt returned a parseable project. */
  repairedScript?: AutomationScript;
  /** True when the single repair POST was made (even if it failed). */
  repairAttempted: boolean;
};

function badgeFor(args: {
  status: 'clean' | 'errors' | 'unchecked';
  errors: number;
  warnings: number;
  beforeErrors?: number;
  python: boolean;
}): SyntaxBadge {
  if (args.status === 'unchecked') return { status: 'unchecked', python: args.python };
  if (args.status === 'clean') {
    if ((args.beforeErrors ?? 0) > 0) {
      return { status: 'repaired', wasErrors: args.beforeErrors ?? 0, warnings: args.warnings };
    }
    return { status: 'clean', warnings: args.warnings };
  }
  return {
    status: 'errors',
    errors: args.errors,
    warnings: args.warnings,
    ...(args.beforeErrors !== undefined ? { beforeErrors: args.beforeErrors } : {}),
  };
}

/**
 * Check, then at most one repair, then re-check. Pure orchestration over an
 * injectable checker (the UI passes the Worker-backed check; tests inject a
 * stub and mock fetch for the single repair POST).
 */
export async function checkAndRepairOnce(args: {
  script: AutomationScript;
  framework?: string;
  defaultKey: StoredKey;
  tier: Tier;
  input: AutomationRequest;
  check?: (files: InputFile[], framework?: string) => Promise<FileReport[]>;
  onStage?: (stage: 'check' | 'repair') => void;
}): Promise<CheckRepairResult> {
  const check = args.check ?? checkFiles;
  const files = automationFiles(args.script).map(([name, code]) => ({ name, code }));
  const frameworkName = args.framework ?? args.input.framework ?? '';

  args.onStage?.('check');
  const reports = await check(files, args.framework ?? args.input.framework);
  const status = summarizeReports(reports);
  const errors = countErrors(reports);
  const warnings = countWarnings(reports);
  // Python is detected from the files as well as the framework: whatever the
  // request said, Python output is not checked in this phase.
  const python = frameworkName.endsWith('(Python)') || reports.some((r) => r.language === 'python');
  if (status !== 'errors') {
    return {
      badge: badgeFor({ status, errors, warnings, python }),
      beforeErrors: 0,
      afterErrors: errors,
      warnings,
      reports,
      repairAttempted: false,
    };
  }

  args.onStage?.('repair');
  const outcome = await requestRepair({
    input: args.input,
    script: args.script,
    reports,
    defaultKey: args.defaultKey,
    tier: args.tier,
  });
  if (!outcome.repaired) {
    return {
      badge: badgeFor({ status: 'errors', errors, warnings, beforeErrors: errors, python }),
      beforeErrors: errors,
      afterErrors: errors,
      warnings,
      reports,
      repairAttempted: true,
    };
  }
  const afterFiles = automationFiles(outcome.script).map(([name, code]) => ({ name, code }));
  const afterReports = await check(afterFiles, args.framework ?? args.input.framework);
  const afterStatus = summarizeReports(afterReports);
  const afterErrors = countErrors(afterReports);
  const afterWarnings = countWarnings(afterReports);
  return {
    badge: badgeFor({
      status: afterStatus,
      errors: afterErrors,
      warnings: afterWarnings,
      beforeErrors: errors,
      python,
    }),
    beforeErrors: errors,
    afterErrors,
    warnings: afterWarnings,
    reports: afterReports,
    repairedScript: outcome.script,
    repairAttempted: true,
  };
}
