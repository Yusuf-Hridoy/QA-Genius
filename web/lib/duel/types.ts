/**
 * Ambiguity Duel types. The Zod schemas live with the internal generator
 * kinds (`lib/duel/story-interpretation/`, `lib/duel/duel-compare/`); this
 * module holds the shared TypeScript shapes including the deterministic
 * additions computed in code (agreementRatio, highlights).
 */
export type InterpretationRule = {
  topic: string;
  reading: string;
  sourcePhrase: string;
};

export type InterpretationNumber = {
  name: string;
  value: string;
  sourcePhrase: string;
};

export type Interpretation = {
  actors: string[];
  preconditions: string[];
  rules: InterpretationRule[];
  numbers: InterpretationNumber[];
  outcomes: string[];
  assumptions: string[];
};

export type DuelSeverity = 'high' | 'medium' | 'low';

export type DuelFork = {
  topic: string;
  readingA: string;
  readingB: string;
  sourcePhrase: string;
  severity: DuelSeverity;
  suggestedRewrite: string;
};

export type DuelHighlight = {
  /** Exact substring from the story (found verbatim, case-insensitive). */
  phrase: string;
  /** Index into forks. */
  forkIndex: number;
  /** Position of the first verbatim occurrence in the story text. */
  start: number;
  end: number;
};

export type DuelResult = {
  a: Interpretation;
  b: Interpretation;
  forks: DuelFork[];
  agreements: string[];
  /** Deterministic: agreements / (agreements + forks), 0 when both empty. */
  agreementRatio: number;
  /** Deterministic: forks whose sourcePhrase was found verbatim in the story. */
  highlights: DuelHighlight[];
};
