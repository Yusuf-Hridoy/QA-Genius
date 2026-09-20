/**
 * Traceability chips (deterministic, Phase 2 §2.2). Parses each test case's
 * `traceability` string for AC-n references; matched ids become accent pills,
 * anything else a neutral pill with the raw text.
 */

const AC_REF = /AC-(\d+)/gi;

/** Extract ordered, deduped `AC-n` ids (case-insensitive, `AC-04` → `AC-4`). */
export function parseTraceabilityRefs(traceability: string): string[] {
  const ids: string[] = [];
  const seen = new Set<string>();
  AC_REF.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = AC_REF.exec(traceability)) !== null) {
    const id = `AC-${parseInt(match[1] as string, 10)}`;
    if (!seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
  }
  return ids;
}

export type Coverage = {
  total: number;
  covered: number;
  coveredIds: string[];
  uncoveredIds: string[];
};

/** Covered = criteria referenced by ≥ 1 case. Counts only parsed ids. */
export function computeCoverage(
  criteriaIds: string[],
  cases: Array<{ traceability: string }>,
): Coverage {
  const referenced = new Set<string>();
  for (const c of cases) {
    for (const id of parseTraceabilityRefs(c.traceability ?? '')) referenced.add(id);
  }
  const coveredIds = criteriaIds.filter((id) => referenced.has(id));
  return {
    total: criteriaIds.length,
    covered: coveredIds.length,
    coveredIds,
    uncoveredIds: criteriaIds.filter((id) => !referenced.has(id)),
  };
}

/** Instructions text for the "generate cases for uncovered" recovery path. */
export function uncoveredInstructions(uncoveredIds: string[]): string {
  return `Add test cases covering: ${uncoveredIds.join(', ')}. Keep all existing cases unchanged.`;
}
