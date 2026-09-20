import { describe, expect, it } from 'vitest';
import { PREFILL_LIMIT, buildScenarioPrefill } from '@/lib/pipeline/automation-prefill';

describe('buildScenarioPrefill', () => {
  it('formats one line per case joined by blank lines', () => {
    const { text, truncated } = buildScenarioPrefill([
      {
        id: 'TC-001',
        title: 'Locks the account',
        category: 'Functional',
        pre_conditions: 'pre',
        steps: ['Fail once', 'Fail twice'],
        expected_result: 'Locked',
        priority: 'High',
        automation_feasibility: 'High',
        automation_effort: 'Low',
        tags: [],
        traceability: 'AC-1',
      },
    ]);
    expect(truncated).toBe(false);
    expect(text).toBe('TC-001 Locks the account: Fail once; Fail twice → Locked');
  });

  it('truncates at the limit with a visible flag', () => {
    const big = buildScenarioPrefill(
      Array.from({ length: 40 }, (_, i) => ({
        id: `TC-0${i + 1}`,
        title: `Case number ${i + 1} with a fairly long descriptive title for padding`,
        category: 'Functional',
        pre_conditions: 'pre',
        steps: ['Do the first thing', 'Do the second thing', 'Verify the third thing'],
        expected_result: 'The expected observable outcome is described here in detail',
        priority: 'High',
        automation_feasibility: 'High',
        automation_effort: 'Low',
        tags: [],
        traceability: 'AC-1',
      })),
    );
    expect(big.truncated).toBe(true);
    expect(big.text.length).toBe(PREFILL_LIMIT);
  });
});
