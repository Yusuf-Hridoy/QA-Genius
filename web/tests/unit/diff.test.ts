import { describe, expect, it } from 'vitest';
import type { TestCase } from '@/lib/generators/test-cases/schema';
import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { diffTestCases } from '@/lib/diff/test-cases';
import { diffStory } from '@/lib/diff/story';
import { stepsDiff, titleSimilarity, wordDiff } from '@/lib/diff/text';

function makeCase(id: string, title: string, overrides: Partial<TestCase> = {}): TestCase {
  return {
    id,
    title,
    category: 'Functional',
    pre_conditions: 'pre',
    steps: ['Open the page', 'Submit the form'],
    expected_result: 'The record is saved',
    priority: 'High',
    automation_feasibility: 'High',
    automation_effort: 'Low',
    tags: [],
    traceability: 'AC-1',
    ...overrides,
  };
}

function makeAnalysis(overrides: Partial<AmbiguityAnalysis> = {}): AmbiguityAnalysis {
  return {
    ambiguity_score: 40,
    clarity_label: 'Mostly Clear',
    invest_overall: 'PARTIAL',
    invest_independent: 'PASS',
    invest_negotiable: 'PASS',
    invest_valuable: 'PASS',
    invest_estimable: 'PASS',
    invest_small: 'PASS',
    invest_testable: 'PASS',
    vague_phrases: [],
    missing_elements: ['No error handling specified'],
    suggested_rewrites: [],
    generated_acceptance_criteria: ['Scenario: Happy path\n  Given a user\n  Then it works'],
    risks: [],
    ...overrides,
  };
}

describe('titleSimilarity', () => {
  it('matches at the 0.6 boundary', () => {
    expect(titleSimilarity('Alpha beta gamma delta', 'Alpha beta gamma epsilon')).toBeCloseTo(0.6);
    expect(titleSimilarity('Alpha beta gamma delta', 'Alpha beta zeta epsilon')).toBeLessThan(0.6);
  });
});

describe('diffTestCases', () => {
  it('matches by id and reports unchanged', () => {
    const diff = diffTestCases([makeCase('TC-001', 'Same')], [makeCase('TC-001', 'Same')]);
    expect(diff.unchanged).toBe(1);
    expect(diff.changed).toBe(0);
  });

  it('matches by title similarity across ids', () => {
    const diff = diffTestCases(
      [makeCase('TC-001', 'Alpha beta gamma delta')],
      [makeCase('TC-009', 'Alpha beta gamma epsilon')],
    );
    expect(diff.changed).toBe(1);
    expect(diff.added).toBe(0);
    expect(diff.removed).toBe(0);
  });

  it('reports added and removed cases', () => {
    const diff = diffTestCases(
      [makeCase('TC-001', 'Alpha beta gamma delta'), makeCase('TC-002', 'Something else entirely')],
      [
        makeCase('TC-001', 'Alpha beta gamma delta'),
        makeCase('TC-009', 'Brand new unrelated case here'),
      ],
    );
    expect(diff.unchanged).toBe(1);
    expect(diff.added).toBe(1);
    expect(diff.removed).toBe(1);
  });

  it('detects changed fields with word and steps diffs', () => {
    const diff = diffTestCases(
      [makeCase('TC-001', 'Old title here', { steps: ['A', 'B', 'C'] })],
      [makeCase('TC-001', 'New title here', { steps: ['A', 'C', 'D'] })],
    );
    expect(diff.changed).toBe(1);
    const entry = diff.cases[0];
    expect(entry?.changedFields).toContain('title');
    expect(entry?.changedFields).toContain('steps');
    const words = (entry?.titleDiff ?? []).map((p) => p.value).join('');
    expect(words).toContain('New');
    expect(words).toContain('Old');
    expect(entry?.stepsOps).toEqual([
      { op: 'same', text: 'A' },
      { op: 'removed', text: 'B' },
      { op: 'same', text: 'C' },
      { op: 'added', text: 'D' },
    ]);
  });
});

describe('stepsDiff and wordDiff', () => {
  it('aligns step lists with LCS', () => {
    expect(stepsDiff(['A', 'B'], ['A', 'B'])).toEqual([
      { op: 'same', text: 'A' },
      { op: 'same', text: 'B' },
    ]);
  });

  it('marks added and removed words', () => {
    const parts = wordDiff('old title here', 'new title here');
    expect(parts.some((p) => p.added && p.value.includes('new'))).toBe(true);
    expect(parts.some((p) => p.removed && p.value.includes('old'))).toBe(true);
  });
});

describe('diffStory', () => {
  it('diffs scalars, sets, and criteria', () => {
    const diff = diffStory(
      makeAnalysis(),
      makeAnalysis({
        clarity_label: 'Needs Work',
        missing_elements: ['No error handling specified', 'No rate limiting described'],
        generated_acceptance_criteria: [
          'Scenario: Happy path\n  Given a user\n  Then it works well',
        ],
      }),
    );
    expect(diff.changed).toBe(true);
    expect(diff.scalars.find((s) => s.field === 'clarity_label')?.changed).toBe(true);
    expect(diff.scalars.find((s) => s.field === 'ambiguity_score')?.changed).toBe(false);
    const missing = diff.arrays.find((a) => a.field === 'missing_elements');
    expect(missing?.added).toEqual(['No rate limiting described']);
    expect(diff.criteria.kept[0]?.changed).toBe(true);
  });

  it('reports unchanged for identical analyses', () => {
    expect(diffStory(makeAnalysis(), makeAnalysis()).changed).toBe(false);
  });
});
