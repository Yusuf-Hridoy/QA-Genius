import { describe, expect, it } from 'vitest';
import { agreementRatio, findHighlights } from '@/lib/duel/highlights';

const STORY =
  'As a shopper, I want my account to lock after several failed login attempts so that my account stays secure, and it may unlock after some time or stay locked until I reset my password.';

describe('agreementRatio', () => {
  it('divides agreements by the total', () => {
    expect(agreementRatio(2, 3)).toBeCloseTo(0.4);
  });

  it('is 0 when there is nothing to compare', () => {
    expect(agreementRatio(0, 0)).toBe(0);
  });
});

describe('findHighlights', () => {
  it('finds verbatim phrases and ignores missing ones', () => {
    const highlights = findHighlights(STORY, [
      { sourcePhrase: 'several failed login attempts' },
      { sourcePhrase: 'a phrase that is not in the story' },
    ]);
    expect(highlights).toHaveLength(1);
    expect(highlights[0]?.phrase).toBe('several failed login attempts');
    expect(highlights[0]?.forkIndex).toBe(0);
  });

  it('matches case-insensitively but keeps the story casing', () => {
    const highlights = findHighlights(STORY, [{ sourcePhrase: 'SEVERAL FAILED LOGIN ATTEMPTS' }]);
    expect(highlights).toHaveLength(1);
    expect(highlights[0]?.phrase).toBe('several failed login attempts');
  });

  it('resolves overlaps longest-first with no nested marks', () => {
    const highlights = findHighlights(STORY, [
      { sourcePhrase: 'failed login attempts' },
      { sourcePhrase: 'several failed login attempts' },
    ]);
    expect(highlights).toHaveLength(1);
    expect(highlights[0]?.phrase).toBe('several failed login attempts');
  });

  it('keeps non-overlapping phrases in story order', () => {
    const highlights = findHighlights(STORY, [
      { sourcePhrase: 'it may unlock after some time' },
      { sourcePhrase: 'several failed login attempts' },
    ]);
    expect(highlights.map((h) => h.forkIndex)).toEqual([1, 0]);
    expect(highlights[0]?.start).toBeLessThan(highlights[1]?.start ?? 0);
  });
});
