import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { extractJson, OutputParseError, repairAndParse } from '@/lib/llm/repair';

const schema = z.object({ a: z.number(), b: z.string() });

describe('extractJson', () => {
  it('returns JSON wrapped in prose', () => {
    expect(extractJson('Here is the result:\n{"a":1}\nDone.')).toBe('{"a":1}');
  });

  it('strips markdown fences', () => {
    expect(extractJson('```json\n{"a": 1}\n```')).toBe('{"a": 1}');
  });

  it('throws when no JSON delimiters exist', () => {
    expect(() => extractJson('no json here')).toThrow(OutputParseError);
  });
});

describe('repairAndParse', () => {
  it('parses clean JSON without repair', () => {
    const result = repairAndParse('{"a":1,"b":"x"}', schema);
    expect(result.value).toEqual({ a: 1, b: 'x' });
    expect(result.repaired).toBe(false);
  });

  it('parses fenced JSON as extracted', () => {
    const result = repairAndParse('```json\n{"a":1,"b":"x"}\n```', schema);
    expect(result.repaired).toBe(true);
  });

  it('repairs trailing commas', () => {
    const result = repairAndParse('{"a":1, "b":"x",}', schema);
    expect(result.value).toEqual({ a: 1, b: 'x' });
    expect(result.repaired).toBe(true);
  });

  it('repairs unescaped inner quotes', () => {
    const result = repairAndParse('{"a":1,"b":"say "hi""}', schema);
    expect(result.value.b).toContain('hi');
  });

  it('throws OutputParseError at the extracted stage on truncation', () => {
    try {
      repairAndParse('{"a":1,"b":"cut off', schema);
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(OutputParseError);
      expect((error as OutputParseError).stage).toBe('extracted');
    }
  });

  it('throws OutputParseError at the repaired stage when repair cannot satisfy the schema', () => {
    try {
      repairAndParse('{"a":1,"b":}', schema);
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(OutputParseError);
      expect((error as OutputParseError).stage).toBe('repaired');
    }
  });

  it('surfaces Zod issues as the parse cause', () => {
    try {
      repairAndParse('{"a":"not-a-number","b":"x"}', schema);
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(OutputParseError);
      expect((error as Error).cause).toBeInstanceOf(z.ZodError);
    }
  });
});
