'use client';

import type { AutomationScript } from '@/lib/generators/automation-script/schema';
import type { FileReport } from './syntax-check/types';

export type SyntaxBadge =
  | { status: 'checking' }
  | { status: 'repairing' }
  | { status: 'clean'; warnings: number }
  | { status: 'repaired'; wasErrors: number; warnings: number }
  | { status: 'errors'; errors: number; warnings: number; beforeErrors?: number }
  | { status: 'unchecked'; python: boolean };

export type SyntaxSummary = {
  badge: SyntaxBadge;
  /** Error count before the repair attempt (for the before → after line). */
  beforeErrors: number;
  /** Error count after the final check. */
  afterErrors: number;
  warnings: number;
  reports: FileReport[];
  /** Hash of the output this summary describes (stale summaries are ignored). */
  outputHash: string;
  /** Hash of the adopted repaired output, when a repair was adopted. */
  repairedHash?: string;
  /** Pre-repair project for the "Download original" link. */
  original?: AutomationScript;
};

/** Short deterministic hash of a JSON value (cache keys, not security). */
export function hashJson(value: unknown): string {
  const text = JSON.stringify(value) ?? '';
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash * 33 + text.charCodeAt(i)) >>> 0) as number;
  }
  return `${text.length}:${hash.toString(36)}`;
}

const STORAGE_PREFIX = 'qag.syntax.';

function storageKey(kind: string): string {
  return `${STORAGE_PREFIX}${kind}`;
}

/**
 * Latest syntax summary per generator kind, mirrored to sessionStorage so
 * exports (rendered by GeneratorScreen from the adopted output) include the
 * SYNTAX-CHECK.md summary after a repair remount.
 */
export function setSyntaxSummary(kind: string, summary: SyntaxSummary): void {
  try {
    sessionStorage.setItem(storageKey(kind), JSON.stringify(summary));
  } catch {
    // storage unavailable — exports skip the summary
  }
}

export function getSyntaxSummary(kind: string): SyntaxSummary | undefined {
  try {
    const raw = sessionStorage.getItem(storageKey(kind));
    if (!raw) return undefined;
    return JSON.parse(raw) as SyntaxSummary;
  } catch {
    return undefined;
  }
}

export function clearSyntaxSummary(kind: string): void {
  try {
    sessionStorage.removeItem(storageKey(kind));
  } catch {
    // ignore
  }
}
