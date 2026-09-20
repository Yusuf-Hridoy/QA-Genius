import { beforeEach, describe, expect, it } from 'vitest';
import {
  CURRENT_KEY,
  MAX_RECENTS,
  RECENTS_KEY,
  evictRecents,
  loadCurrent,
  loadRecents,
  newRun,
  useRunStore,
} from '@/lib/store/run';
import type { Run } from '@/lib/pipeline/types';

function resetStore(): void {
  window.sessionStorage.clear();
  window.localStorage.clear();
  useRunStore.setState({ run: newRun('Aurora Storefront'), recents: [] });
}

function storedCurrent(): Run {
  const raw = window.sessionStorage.getItem(CURRENT_KEY);
  expect(raw).not.toBeNull();
  return JSON.parse(raw as string) as Run;
}

describe('run store criteria', () => {
  beforeEach(resetStore);

  it('recomputes AC ids on reorder', () => {
    const s = useRunStore.getState();
    s.setCriteria(['First', 'Second', 'Third'], 'story');
    expect(useRunStore.getState().run.criteria?.items.map((c) => c.id)).toEqual([
      'AC-1',
      'AC-2',
      'AC-3',
    ]);
    useRunStore.getState().reorderCriteria(0, 2);
    const items = useRunStore.getState().run.criteria?.items ?? [];
    expect(items.map((c) => c.text)).toEqual(['Second', 'Third', 'First']);
    expect(items.map((c) => c.id)).toEqual(['AC-1', 'AC-2', 'AC-3']);
  });

  it('recomputes AC ids on delete', () => {
    useRunStore.getState().setCriteria(['A', 'B', 'C'], 'manual');
    useRunStore.getState().removeCriterion(0);
    const items = useRunStore.getState().run.criteria?.items ?? [];
    expect(items.map((c) => c.text)).toEqual(['B', 'C']);
    expect(items.map((c) => c.id)).toEqual(['AC-1', 'AC-2']);
  });

  it('adds, updates, and ignores out-of-range operations', () => {
    const s = useRunStore.getState();
    s.setCriteria(['A'], 'manual');
    s.addCriterion('B');
    s.updateCriterion(0, 'A2');
    expect(useRunStore.getState().run.criteria?.items.map((c) => c.text)).toEqual(['A2', 'B']);
    // Out of range: no change, no crash.
    s.updateCriterion(9, 'X');
    s.removeCriterion(-1);
    s.reorderCriteria(0, 9);
    s.reorderCriteria(0, 0);
    expect(useRunStore.getState().run.criteria?.items.map((c) => c.text)).toEqual(['A2', 'B']);
  });
});

describe('run store test-case history', () => {
  beforeEach(resetStore);

  const input = {
    user_story: 'As a shopper, I want cart quantity limits so the warehouse can fulfil orders.',
    coverage_focus: ['Functional'] as Array<'Functional'>,
  };

  function listWithTitles(titles: string[]) {
    return {
      test_cases: titles.map((title, i) => ({
        id: `TC-00${i + 1}`,
        title,
        category: 'Functional',
        pre_conditions: 'pre',
        steps: ['step'],
        expected_result: 'expected',
        priority: 'High',
        automation_feasibility: 'High',
        automation_effort: 'Low',
        tags: [],
        traceability: 'AC-1',
      })),
      summary: {
        total_generated: titles.length,
        category_breakdown: [],
        priority_breakdown: [],
        automation_coverage_potential: 'high',
        coverage_gaps: [],
        recommendations: [],
      },
    };
  }

  it('pushes history on accept and restores on undo', () => {
    const s = useRunStore.getState();
    s.setTestCases(input, listWithTitles(['One', 'Two']));
    const revised = listWithTitles(['One', 'Two', 'Three']);
    useRunStore.getState().acceptTestCasesRevision(revised);
    let current = useRunStore.getState().run.testCases;
    expect(current?.output?.test_cases.map((c) => c.title)).toEqual(['One', 'Two', 'Three']);
    expect(current?.history).toHaveLength(1);

    useRunStore.getState().undoTestCases();
    current = useRunStore.getState().run.testCases;
    expect(current?.output?.test_cases.map((c) => c.title)).toEqual(['One', 'Two']);
    expect(current?.history).toHaveLength(0);
  });

  it('undo with empty history is a no-op', () => {
    useRunStore.getState().setTestCases(input, listWithTitles(['One']));
    useRunStore.getState().undoTestCases();
    expect(useRunStore.getState().run.testCases?.output?.test_cases).toHaveLength(1);
  });
});

describe('run store persistence', () => {
  beforeEach(resetStore);

  it('round-trips the current run through sessionStorage', () => {
    const s = useRunStore.getState();
    s.setStory(
      {
        user_story: 'As a shopper, I want to save items for later so I can buy them next visit.',
        story_type: 'User Story',
      },
      undefined,
      undefined,
    );
    s.setCriteria(['Must persist'], 'story');
    const fromStorage = loadCurrent();
    expect(fromStorage?.id).toBe(useRunStore.getState().run.id);
    expect(fromStorage?.criteria?.items.map((c) => c.text)).toEqual(['Must persist']);
    expect(storedCurrent().story?.input.user_story).toContain('save items');
  });

  it('caps recent runs and evicts the oldest', () => {
    // Newest first, as stored: run-11 is the newest.
    const runs: Run[] = Array.from({ length: MAX_RECENTS + 2 }, (_, i) => ({
      ...newRun('Aurora Storefront'),
      id: `run-${MAX_RECENTS + 1 - i}`,
    }));
    const evicted = evictRecents(runs);
    expect(evicted).toHaveLength(MAX_RECENTS);
    expect(evicted[0]?.id).toBe(`run-${MAX_RECENTS + 1}`);
    expect(evicted.map((r) => r.id)).not.toContain('run-0');
  });

  it('evicts under the 1 MB total budget', () => {
    const big = 'x'.repeat(600_000);
    const runs: Run[] = [0, 1].map((i) => ({
      ...newRun('Aurora Storefront'),
      id: `big-${i}`,
      story: {
        input: {
          user_story: `As a shopper I want ${big} so that everything works fine here.`,
          story_type: 'User Story',
        },
      },
    }));
    const evicted = evictRecents(runs);
    expect(evicted.length).toBeLessThan(runs.length);
    // Newest (first) survives; the oldest is evicted.
    expect(evicted[0]?.id).toBe('big-0');
  });

  it('writes recents to localStorage on change', () => {
    useRunStore.getState().setCriteria(['R'], 'manual');
    const recents = loadRecents();
    expect(recents.length).toBeGreaterThan(0);
    expect(recents[0]?.criteria?.items.map((c) => c.text)).toEqual(['R']);
    expect(window.localStorage.getItem(RECENTS_KEY)).not.toBeNull();
  });

  it('adopts a shared run with a fresh id', () => {
    const shared: Run = { ...newRun('Shared'), projectName: 'Shared project' };
    useRunStore.getState().adoptSharedRun(shared);
    const current = useRunStore.getState().run;
    expect(current.projectName).toBe('Shared project');
    expect(current.id).not.toBe(shared.id);
  });
});
