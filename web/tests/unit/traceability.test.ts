import { describe, expect, it } from 'vitest';
import {
  computeCoverage,
  parseTraceabilityRefs,
  uncoveredInstructions,
} from '@/lib/traceability/parse';

describe('parseTraceabilityRefs', () => {
  it('parses a single id', () => {
    expect(parseTraceabilityRefs('AC-2')).toEqual(['AC-2']);
  });

  it('parses comma-separated ids', () => {
    expect(parseTraceabilityRefs('AC-1, AC-3')).toEqual(['AC-1', 'AC-3']);
  });

  it('is case-insensitive', () => {
    expect(parseTraceabilityRefs('ac-4')).toEqual(['AC-4']);
  });

  it('returns an empty list for free text', () => {
    expect(parseTraceabilityRefs('lock after 5 consecutive failures')).toEqual([]);
  });

  it('dedupes and normalizes leading zeros', () => {
    expect(parseTraceabilityRefs('AC-04 and AC-4 and AC-2')).toEqual(['AC-4', 'AC-2']);
  });
});

describe('computeCoverage', () => {
  it('counts covered criteria and lists the uncovered', () => {
    const coverage = computeCoverage(
      ['AC-1', 'AC-2', 'AC-3'],
      [{ traceability: 'AC-1, AC-3' }, { traceability: 'free text without refs' }],
    );
    expect(coverage).toEqual({
      total: 3,
      covered: 2,
      coveredIds: ['AC-1', 'AC-3'],
      uncoveredIds: ['AC-2'],
    });
  });

  it('builds the uncovered recovery instructions', () => {
    expect(uncoveredInstructions(['AC-3', 'AC-5'])).toBe(
      'Add test cases covering: AC-3, AC-5. Keep all existing cases unchanged.',
    );
  });
});
