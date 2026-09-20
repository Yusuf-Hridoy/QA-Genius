import type { DuelHighlight } from './types';

/** Deterministic: agreements / (agreements + forks), 0 when both are empty. */
export function agreementRatio(agreementCount: number, forkCount: number): number {
  const total = agreementCount + forkCount;
  if (total === 0) return 0;
  return agreementCount / total;
}

type Range = { start: number; end: number; forkIndex: number; phrase: string };

function firstOccurrence(
  lowerStory: string,
  lowerPhrase: string,
): { start: number; end: number } | null {
  if (!lowerPhrase) return null;
  const start = lowerStory.indexOf(lowerPhrase);
  if (start === -1) return null;
  return { start, end: start + lowerPhrase.length };
}

/**
 * Deterministic highlight extraction: every fork whose `sourcePhrase` is
 * found verbatim (case-insensitive) in the story. Missing phrases are kept
 * in the fork list but not highlighted. Overlaps resolve longest-first with
 * no nested marks.
 */
export function findHighlights(
  story: string,
  forks: Array<{ sourcePhrase: string }>,
): DuelHighlight[] {
  const lowerStory = story.toLowerCase();
  const candidates: Range[] = [];
  forks.forEach((fork, forkIndex) => {
    const phrase = fork.sourcePhrase ?? '';
    if (!phrase.trim()) return;
    const found = firstOccurrence(lowerStory, phrase.toLowerCase());
    if (!found) return;
    candidates.push({
      ...found,
      forkIndex,
      phrase: story.slice(found.start, found.end),
    });
  });

  // Longest first so a long phrase wins over a nested short one.
  candidates.sort((a, b) => b.phrase.length - a.phrase.length || a.start - b.start);
  const taken: Range[] = [];
  for (const c of candidates) {
    const overlaps = taken.some((t) => c.start < t.end && t.start < c.end);
    if (!overlaps) taken.push(c);
  }
  taken.sort((a, b) => a.start - b.start);
  return taken.map(({ phrase, forkIndex, start, end }) => ({ phrase, forkIndex, start, end }));
}
