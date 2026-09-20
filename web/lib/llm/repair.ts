import { jsonrepair } from 'jsonrepair';
import type { z } from 'zod';

export type RepairStage = 'raw' | 'extracted' | 'repaired';

export class OutputParseError extends Error {
  readonly stage: RepairStage;
  readonly excerpt: string;

  constructor(stage: RepairStage, text: string, options?: { cause?: unknown }) {
    super(`Could not parse model output (stage: ${stage}).`, options);
    this.name = 'OutputParseError';
    this.stage = stage;
    this.excerpt = text.slice(0, 500);
  }
}

/**
 * Strip markdown fences and surrounding prose; return from the first { or [ to the
 * last } or ] (ported from v1 json_repair_utils.extract_json).
 */
export function extractJson(text: string): string {
  let t = text.trim();
  t = t
    .replace(/^```(?:json)?[ \t]*/i, '')
    .replace(/```[ \t]*$/, '')
    .trim();

  const startCandidates = [t.indexOf('{'), t.indexOf('[')].filter((i) => i >= 0);
  const endCandidates = [t.lastIndexOf('}'), t.lastIndexOf(']')].filter((i) => i >= 0);
  if (startCandidates.length === 0 || endCandidates.length === 0) {
    throw new OutputParseError('extracted', text);
  }
  const start = Math.min(...startCandidates);
  const end = Math.max(...endCandidates);
  if (end <= start) {
    throw new OutputParseError('extracted', text);
  }
  return t.slice(start, end + 1);
}

/**
 * 1) JSON.parse the raw text
 * 2) extractJson → JSON.parse
 * 3) jsonrepair(extractJson) → JSON.parse
 * Each parsed value is validated against the Zod schema. Throws OutputParseError
 * with the failing stage when nothing works.
 */
export function repairAndParse<S extends z.ZodType>(
  text: string,
  schema: S,
): { value: z.output<S>; repaired: boolean } {
  try {
    return { value: schema.parse(JSON.parse(text)), repaired: false };
  } catch {
    // continue to extraction
  }

  let extracted: string;
  try {
    extracted = extractJson(text);
  } catch (error) {
    throw error instanceof OutputParseError
      ? error
      : new OutputParseError('extracted', text, { cause: error });
  }

  try {
    return { value: schema.parse(JSON.parse(extracted)), repaired: true };
  } catch {
    // continue to repair
  }

  try {
    return { value: schema.parse(JSON.parse(jsonrepair(extracted))), repaired: true };
  } catch (error) {
    throw new OutputParseError('repaired', text, { cause: error });
  }
}
