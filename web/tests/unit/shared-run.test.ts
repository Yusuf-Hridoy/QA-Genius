import { describe, expect, it } from 'vitest';
import { decodeShare, encodeShare } from '@/lib/share/codec';
import {
  parseSharedRun,
  sharedCriteria,
  sharedDuel,
  sharedStoryInput,
  sharedStoryOutput,
  sharedTestCases,
} from '@/lib/share/shared-run';
import { newRun } from '@/lib/store/run';
import type { Run } from '@/lib/pipeline/types';
import type { DuelResult } from '@/lib/duel/types';
import sampleA from '../../fixtures/story_interpretation/sample-a.json';
import sampleB from '../../fixtures/story_interpretation/sample-b.json';
import duelOutput from '../../fixtures/duel_compare/sample-output.json';

function richRun(): Run {
  const run = newRun('Aurora Storefront');
  run.story = {
    input: {
      user_story: 'As a shopper, I want my account to lock after several failed login attempts.',
      story_type: 'User Story',
    },
    output: {
      ambiguity_score: 60,
      clarity_label: 'Needs Work',
      invest_overall: 'PARTIAL',
      invest_independent: 'PASS',
      invest_negotiable: 'PASS',
      invest_valuable: 'PASS',
      invest_estimable: 'PASS',
      invest_small: 'PASS',
      invest_testable: 'PASS',
      vague_phrases: [],
      missing_elements: [],
      suggested_rewrites: [],
      generated_acceptance_criteria: ['Scenario: X\n  Given y'],
      risks: [],
    },
  };
  run.criteria = { items: [{ id: 'AC-1', text: 'First' }], source: 'story' };
  run.duel = {
    a: sampleA,
    b: sampleB,
    forks: duelOutput.forks,
    agreements: duelOutput.agreements,
    agreementRatio: 0.4,
    highlights: [{ phrase: 'several failed login attempts', forkIndex: 0, start: 10, end: 40 }],
  } as unknown as DuelResult;
  return run;
}

describe('shared run parsers', () => {
  it('parses every section of a rich run', () => {
    const fragment = encodeShare(richRun(), { name: 'Aurora Storefront', stack: 'Next.js' });
    const run = parseSharedRun(decodeShare(fragment).run);
    expect(run).not.toBeNull();
    const valid = run as Run;
    expect(sharedStoryInput(valid)).toContain('several failed login attempts');
    expect(sharedStoryOutput(valid)?.clarity_label).toBe('Needs Work');
    expect(sharedCriteria(valid)).toEqual([{ id: 'AC-1', text: 'First' }]);
    expect(sharedDuel(valid)?.forks).toHaveLength(3);
    expect(sharedTestCases(valid)).toBeUndefined();
  });

  it('rejects runs without an id and invalid sections', () => {
    expect(parseSharedRun({})).toBeNull();
    expect(parseSharedRun(null)).toBeNull();
    const run = newRun();
    run.criteria = { items: [{ id: 'AC-1' }] } as unknown as Run['criteria'];
    expect(sharedCriteria(run)).toEqual([]);
    expect(sharedDuel(run)).toBeUndefined();
    expect(sharedStoryOutput(run)).toBeUndefined();
    expect(sharedStoryInput(run)).toBeUndefined();
  });
});
