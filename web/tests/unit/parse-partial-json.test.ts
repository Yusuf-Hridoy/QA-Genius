import { describe, expect, it } from 'vitest';
import { parsePartialJson } from '@/lib/client/parse-partial-json';

describe('parsePartialJson', () => {
  it('parses complete JSON', () => {
    expect(parsePartialJson('{"a":1,"b":[2,3]}')).toEqual({ a: 1, b: [2, 3] });
  });

  it('returns undefined for empty or garbage input', () => {
    expect(parsePartialJson('')).toBeUndefined();
    expect(parsePartialJson('   ')).toBeUndefined();
    expect(parsePartialJson('hello world')).toBeUndefined();
  });

  it('completes a truncated object at a value boundary', () => {
    expect(parsePartialJson('{"a":1,"b":"x","c":')).toEqual({ a: 1, b: 'x' });
  });

  it('completes a partially-arrived nested array', () => {
    expect(parsePartialJson('{"items":[{"id":1},{"id":2')).toEqual({
      items: [{ id: 1 }, { id: 2 }],
    });
  });

  it('drops a key whose value has not started', () => {
    expect(parsePartialJson('{"a":1,"b":')).toEqual({ a: 1 });
  });

  it('handles a mid-string truncation by ending at the last safe token', () => {
    const result = parsePartialJson('{"title":"Lockout flo');
    expect(result).toEqual({});
  });
});
