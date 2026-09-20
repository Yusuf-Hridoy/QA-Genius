import { diffWords, type Change } from 'diff';

/** Minimal stopword list for title-similarity matching. */
const STOPWORDS = new Set([
  'the',
  'a',
  'an',
  'and',
  'or',
  'of',
  'to',
  'for',
  'with',
  'on',
  'in',
  'is',
  'are',
  'be',
  'after',
  'before',
  'when',
  'then',
  'that',
  'this',
  'it',
  'as',
  'by',
  'from',
  'at',
  'into',
  'over',
  's',
]);

/** Lowercase, strip punctuation, drop stopwords. */
export function normalizeTokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length > 0 && !STOPWORDS.has(t));
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  let intersection = 0;
  for (const t of a) if (b.has(t)) intersection += 1;
  return intersection / (a.size + b.size - intersection);
}

/** Normalized token Jaccard similarity of two titles. */
export function titleSimilarity(a: string, b: string): number {
  return jaccard(new Set(normalizeTokens(a)), new Set(normalizeTokens(b)));
}

/** Title-similarity threshold for matching cases across revisions. */
export const TITLE_MATCH_THRESHOLD = 0.6;

/** Word-level diff of two strings (title, expected result). */
export function wordDiff(before: string, after: string): Change[] {
  return diffWords(before ?? '', after ?? '');
}

export type StepOp = { op: 'same' | 'added' | 'removed'; text: string };

/**
 * Array LCS diff of two step lists. Returns ops in order; matches steps by
 * exact string equality after trimming.
 */
export function stepsDiff(before: string[], after: string[]): StepOp[] {
  const a = (before ?? []).map((s) => s.trim());
  const b = (after ?? []).map((s) => s.trim());
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      const same = (a[i] as string) === (b[j] as string);
      dp[i]![j] = same
        ? ((dp[i + 1]?.[j + 1] ?? 0) as number) + 1
        : Math.max((dp[i + 1]?.[j] ?? 0) as number, (dp[i]?.[j + 1] ?? 0) as number);
    }
  }
  const ops: StepOp[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      ops.push({ op: 'same', text: b[j] as string });
      i += 1;
      j += 1;
    } else if ((dp[i + 1]?.[j] ?? 0) >= (dp[i]?.[j + 1] ?? 0)) {
      ops.push({ op: 'removed', text: a[i] as string });
      i += 1;
    } else {
      ops.push({ op: 'added', text: b[j] as string });
      j += 1;
    }
  }
  while (i < m) {
    ops.push({ op: 'removed', text: a[i] as string });
    i += 1;
  }
  while (j < n) {
    ops.push({ op: 'added', text: b[j] as string });
    j += 1;
  }
  return ops;
}
