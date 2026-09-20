import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import type { StoryAnalyzerRequest } from '@/lib/generators/story-analyzer/request';
import type { TestCaseList } from '@/lib/generators/test-cases/schema';
import type { TestCasesRequest } from '@/lib/generators/test-cases/request';
import type { DuelResult } from '@/lib/duel/types';

/** Acceptance criterion with a stable display id (AC-1, AC-2, … in array order). */
export type AcceptanceCriterion = { id: string; text: string };

/** Subset of the streaming footer meta persisted with a run step. No keys, no headers. */
export type GenerateMeta = {
  provider?: string;
  model?: string;
  tier?: string;
  requestId?: string;
  latencyMs?: number;
  repaired?: boolean;
};

/**
 * Run is the client-side object that carries state across the Requirements
 * pipeline steps. It lives in sessionStorage (`qag.run.current`); a small
 * "recent runs" list lives in localStorage (`qag.runs.v1`).
 */
export type Run = {
  id: string;
  createdAt: string;
  updatedAt: string;
  projectName: string;
  story?: {
    input: StoryAnalyzerRequest;
    output?: AmbiguityAnalysis;
    meta?: GenerateMeta;
  };
  duel?: DuelResult;
  criteria?: {
    items: AcceptanceCriterion[];
    source: 'story' | 'manual';
    /** Manual story text when the run started from scratch (no step 1). */
    manualStory?: string;
  };
  testCases?: {
    input: TestCasesRequest;
    output?: TestCaseList;
    meta?: GenerateMeta;
    history: TestCaseList[];
    /** Card checkboxes in step 3; used for the step 4 prefill. */
    selectedIds?: string[];
  };
  suite?: { fileName: string; importedAt: string; count: number };
  /** Step 4 prefill built from the selected test cases. */
  automation?: { scenarioPrefill: string; truncated: boolean; updatedAt: string };
};

export function criterionId(index: number): string {
  return `AC-${index + 1}`;
}

/** Recompute AC-1..n ids from array order. */
export function withCriterionIds(texts: string[]): AcceptanceCriterion[] {
  return texts.map((text, i) => ({ id: criterionId(i), text }));
}
