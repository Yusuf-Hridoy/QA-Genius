import { normalizeTokens } from '@/lib/diff/text';

export type SuiteMatchStatus = 'covered' | 'similar' | 'gap';

export type SuiteMatch = {
  status: SuiteMatchStatus;
  /** Id of the matched existing-suite row (empty for gaps). */
  suiteId: string;
  score: number;
  /** Title of the matched row, for the tooltip. */
  title: string;
};

/** Similarity thresholds: ≥ covered, ≥ similar, else gap. */
export const COVERED_THRESHOLD = 0.55;
export const SIMILAR_THRESHOLD = 0.35;

/** Light plural stemming for suite matching (trims a trailing `s`). */
export function stemToken(token: string): string {
  if (token.length > 3 && token.endsWith('s') && !token.endsWith('ss')) {
    return token.slice(0, -1);
  }
  return token;
}

/** Normalized, stemmed token multiset of a text. */
export function suiteTokens(text: string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const token of normalizeTokens(text ?? '')) {
    const stemmed = stemToken(token);
    counts.set(stemmed, (counts.get(stemmed) ?? 0) + 1);
  }
  return counts;
}

/**
 * Weighted token Jaccard: title tokens carry weight 2, expected-result
 * tokens weight 1. The model is never consulted for matching.
 */
export function weightedJaccard(
  titleA: string,
  expectedA: string,
  titleB: string,
  expectedB: string,
): number {
  const weighted = new Map<string, [number, number]>();
  const add = (text: string, weight: number, side: 0 | 1) => {
    for (const [token, count] of suiteTokens(text)) {
      const entry = weighted.get(token) ?? [0, 0];
      entry[side] += count * weight;
      weighted.set(token, entry);
    }
  };
  add(titleA, 2, 0);
  add(expectedA, 1, 0);
  add(titleB, 2, 1);
  add(expectedB, 1, 1);
  let intersection = 0;
  let union = 0;
  for (const [a, b] of weighted.values()) {
    intersection += Math.min(a, b);
    union += Math.max(a, b);
  }
  if (union === 0) return 0;
  return intersection / union;
}

export type MatchableCase = { id: string; title: string; expected_result: string };
export type MatchableRow = { id: string; title: string; expected: string };

/**
 * Match every generated case against the existing suite. Returns a match per
 * case id: `covered` (≥ 0.55), `similar` (0.35–0.55), or `gap` (< 0.35).
 */
export function matchSuite(
  cases: MatchableCase[],
  rows: MatchableRow[],
): Record<string, SuiteMatch> {
  const matches: Record<string, SuiteMatch> = {};
  for (const c of cases) {
    let best: { row: MatchableRow; score: number } | null = null;
    for (const row of rows) {
      const score = weightedJaccard(c.title, c.expected_result, row.title, row.expected);
      if (!best || score > best.score) best = { row, score };
    }
    const score = best?.score ?? 0;
    if (best && score >= COVERED_THRESHOLD) {
      matches[c.id] = { status: 'covered', suiteId: best.row.id, score, title: best.row.title };
    } else if (best && score >= SIMILAR_THRESHOLD) {
      matches[c.id] = { status: 'similar', suiteId: best.row.id, score, title: best.row.title };
    } else {
      matches[c.id] = { status: 'gap', suiteId: '', score, title: '' };
    }
  }
  return matches;
}
