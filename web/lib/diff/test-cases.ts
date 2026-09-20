import type { TestCase } from '@/lib/generators/test-cases/schema';
import { TITLE_MATCH_THRESHOLD, stepsDiff, titleSimilarity, wordDiff, type StepOp } from './text';
import type { Change } from 'diff';

export type CaseStatus = 'unchanged' | 'changed' | 'added' | 'removed';

export type CaseDiff = {
  status: CaseStatus;
  /** Id from the current list, or the revised id for added cases. */
  id: string;
  current?: TestCase;
  revised?: TestCase;
  /** Which of title/steps/expected/priority/category differ. */
  changedFields?: string[];
  titleDiff?: Change[];
  expectedDiff?: Change[];
  stepsOps?: StepOp[];
};

export type TestCasesDiff = {
  cases: CaseDiff[];
  added: number;
  changed: number;
  removed: number;
  unchanged: number;
};

const COMPARED_FIELDS = ['title', 'steps', 'expected', 'priority', 'category'] as const;

function stepsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((s, i) => s === b[i]);
}

/**
 * Diff two test-case lists. Matches by `id` first, then by title similarity
 * (normalized token Jaccard ≥ 0.6). Unmatched revised cases are `added`,
 * unmatched current cases are `removed`.
 */
export function diffTestCases(current: TestCase[], revised: TestCase[]): TestCasesDiff {
  const byId = new Map(revised.map((c) => [c.id, c]));
  const usedRevised = new Set<string>();
  const cases: CaseDiff[] = [];

  // Pass 1: id matches.
  const idMatchedCurrent = new Set<string>();
  for (const cur of current) {
    const rev = byId.get(cur.id);
    if (rev) {
      idMatchedCurrent.add(cur.id);
      usedRevised.add(rev.id);
      cases.push(compareCase(cur, rev));
    }
  }

  // Pass 2: title-similarity matches for the rest (best match above threshold).
  const unmatchedCurrent = current.filter((c) => !idMatchedCurrent.has(c.id));
  const unmatchedRevised = revised.filter((c) => !usedRevised.has(c.id));
  const usedRevised2 = new Set<string>();
  for (const cur of unmatchedCurrent) {
    let best: { rev: TestCase; score: number } | null = null;
    for (const rev of unmatchedRevised) {
      if (usedRevised2.has(rev.id)) continue;
      const score = titleSimilarity(cur.title, rev.title);
      if (score >= TITLE_MATCH_THRESHOLD && (!best || score > best.score)) {
        best = { rev, score };
      }
    }
    if (best) {
      usedRevised2.add(best.rev.id);
      cases.push(compareCase(cur, best.rev));
    } else {
      cases.push({ status: 'removed', id: cur.id, current: cur });
    }
  }
  for (const rev of unmatchedRevised) {
    if (!usedRevised2.has(rev.id)) {
      cases.push({ status: 'added', id: rev.id, revised: rev });
    }
  }

  return {
    cases,
    added: cases.filter((c) => c.status === 'added').length,
    changed: cases.filter((c) => c.status === 'changed').length,
    removed: cases.filter((c) => c.status === 'removed').length,
    unchanged: cases.filter((c) => c.status === 'unchanged').length,
  };
}

export function compareCase(cur: TestCase, rev: TestCase): CaseDiff {
  const changedFields: string[] = [];
  if (cur.title !== rev.title) changedFields.push('title');
  if (!stepsEqual(cur.steps ?? [], rev.steps ?? [])) changedFields.push('steps');
  if (cur.expected_result !== rev.expected_result) changedFields.push('expected');
  if (cur.priority !== rev.priority) changedFields.push('priority');
  if (cur.category !== rev.category) changedFields.push('category');

  if (changedFields.length === 0) {
    return { status: 'unchanged', id: cur.id, current: cur, revised: rev };
  }
  return {
    status: 'changed',
    id: cur.id,
    current: cur,
    revised: rev,
    changedFields,
    titleDiff: wordDiff(cur.title, rev.title),
    expectedDiff: wordDiff(cur.expected_result, rev.expected_result),
    stepsOps: stepsDiff(cur.steps ?? [], rev.steps ?? []),
  };
}

export { COMPARED_FIELDS };
