import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { wordDiff } from './text';
import type { Change } from 'diff';

export type StoryScalarDiff = {
  field: string;
  before: string;
  after: string;
  changed: boolean;
};

export type StoryArrayDiff = {
  field: string;
  added: string[];
  removed: string[];
};

export type StoryCriteriaDiff = {
  /** Per-index word diffs for kept lines, plus added/removed lines. */
  kept: Array<{ index: number; diff: Change[]; changed: boolean }>;
  added: string[];
  removed: string[];
};

export type StoryDiff = {
  scalars: StoryScalarDiff[];
  arrays: StoryArrayDiff[];
  criteria: StoryCriteriaDiff;
  changed: boolean;
};

const SCALAR_FIELDS = [
  'ambiguity_score',
  'clarity_label',
  'invest_overall',
  'invest_independent',
  'invest_negotiable',
  'invest_valuable',
  'invest_estimable',
  'invest_small',
  'invest_testable',
] as const;

const STRING_ARRAY_FIELDS = [
  'missing_elements',
  'risks',
  'suggested_rewrites',
  'recommended_split',
] as const;

function scalarOf(analysis: AmbiguityAnalysis | undefined, field: string): string {
  if (!analysis) return '';
  const value = (analysis as unknown as Record<string, unknown>)[field];
  return value === undefined || value === null ? '' : String(value);
}

function arrayOf(analysis: AmbiguityAnalysis | undefined, field: string): string[] {
  if (!analysis) return [];
  const value = (analysis as unknown as Record<string, unknown>)[field];
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function setDiff(before: string[], after: string[]): { added: string[]; removed: string[] } {
  const beforeSet = new Set(before);
  const afterSet = new Set(after);
  return {
    added: after.filter((s) => !beforeSet.has(s)),
    removed: before.filter((s) => !afterSet.has(s)),
  };
}

/**
 * Field-level diff of two story analyses: scalars as changed/unchanged,
 * string arrays as added/removed sets, acceptance criteria with word diffs.
 */
export function diffStory(
  current: AmbiguityAnalysis | undefined,
  revised: AmbiguityAnalysis | undefined,
): StoryDiff {
  const scalars: StoryScalarDiff[] = SCALAR_FIELDS.map((field) => {
    const before = scalarOf(current, field);
    const after = scalarOf(revised, field);
    return { field, before, after, changed: before !== after };
  });

  const arrays: StoryArrayDiff[] = STRING_ARRAY_FIELDS.map((field) => {
    const { added, removed } = setDiff(arrayOf(current, field), arrayOf(revised, field));
    return { field, added, removed };
  });

  // Vague phrases keyed by phrase text.
  const beforePhrases = (current?.vague_phrases ?? []).map((v) => v.phrase);
  const afterPhrases = (revised?.vague_phrases ?? []).map((v) => v.phrase);
  const phraseDiff = setDiff(beforePhrases, afterPhrases);
  arrays.push({ field: 'vague_phrases', added: phraseDiff.added, removed: phraseDiff.removed });

  const beforeCriteria = current?.generated_acceptance_criteria ?? [];
  const afterCriteria = revised?.generated_acceptance_criteria ?? [];
  const kept = beforeCriteria.map((line, index) => {
    const next = afterCriteria[index];
    if (next === undefined) return { index, diff: wordDiff(line, ''), changed: true };
    return { index, diff: wordDiff(line, next), changed: line !== next };
  });
  const criteria: StoryCriteriaDiff = {
    kept,
    added: afterCriteria.slice(beforeCriteria.length),
    removed: beforeCriteria.slice(afterCriteria.length),
  };

  const changed =
    scalars.some((s) => s.changed) ||
    arrays.some((a) => a.added.length > 0 || a.removed.length > 0) ||
    kept.some((k) => k.changed) ||
    criteria.added.length > 0 ||
    criteria.removed.length > 0;

  return { scalars, arrays, criteria, changed };
}
