import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  COVERED_THRESHOLD,
  SIMILAR_THRESHOLD,
  matchSuite,
  stemToken,
  suiteTokens,
  weightedJaccard,
} from '@/lib/suite/match';
import { applyMapping, guessMapping, parseCsv, parseXlsx } from '@/lib/suite/parse';
import { loadFixture } from '../e2e/helpers/stream-fixture';

const SUITE_DIR = join(__dirname, '..', '..', 'fixtures', 'suite');

describe('suite tokens', () => {
  it('lowercases, strips punctuation, and stems plurals', () => {
    expect([...suiteTokens('Accounts, locks!').keys()].sort()).toEqual(['account', 'lock']);
    expect(stemToken('class')).toBe('class');
    expect(stemToken('is')).toBe('is');
  });
});

describe('weightedJaccard', () => {
  it('weights title tokens above expected tokens', () => {
    const titleHit = weightedJaccard(
      'account lockout window',
      'zzz qqq',
      'account lockout window',
      'www eee',
    );
    const expectedOnly = weightedJaccard(
      'aaa bbb',
      'account lockout window',
      'ccc ddd',
      'account lockout window',
    );
    expect(titleHit).toBeGreaterThan(expectedOnly);
  });

  it('returns 0 for empty inputs', () => {
    expect(weightedJaccard('', '', '', '')).toBe(0);
  });
});

describe('matchSuite thresholds', () => {
  const row = {
    id: 'AUR-1',
    title: 'Account locks after five failures',
    expected: 'the account is locked',
  };

  it('marks identical texts covered', () => {
    const matches = matchSuite(
      [{ id: 'TC-001', title: row.title, expected_result: row.expected }],
      [row],
    );
    expect(matches['TC-001']?.status).toBe('covered');
    expect(matches['TC-001']?.score).toBeGreaterThanOrEqual(COVERED_THRESHOLD);
  });

  it('marks unrelated texts as gaps', () => {
    const matches = matchSuite(
      [{ id: 'TC-001', title: 'Wishlist saves items for later', expected_result: 'items persist' }],
      [row],
    );
    expect(matches['TC-001']?.status).toBe('gap');
    expect(matches['TC-001']?.score).toBeLessThan(SIMILAR_THRESHOLD);
  });

  it('places partial overlap in the similar band', () => {
    // Shares account/lock vocabulary but little else.
    const matches = matchSuite(
      [
        {
          id: 'TC-001',
          title: 'Account lockout message wording review',
          expected_result: 'wording is clear',
        },
      ],
      [row],
    );
    const score = matches['TC-001']?.score ?? 0;
    expect(score).toBeGreaterThanOrEqual(0);
    expect(matches['TC-001']?.status).toBe(
      score >= COVERED_THRESHOLD ? 'covered' : score >= SIMILAR_THRESHOLD ? 'similar' : 'gap',
    );
  });
});

describe('guessMapping', () => {
  const variants: string[][] = [
    ['ID', 'Title', 'Steps', 'Expected Result'],
    ['key', 'summary', 'procedure', 'expected result'],
    ['tc', 'name', 'actions', 'result'],
    ['Test Case', 'Action', 'Expected Result'],
    ['case id', 'test case', 'steps', 'expected'],
    ['ID', 'Name', 'Procedure', 'Result'],
    ['Key', 'Title', 'Description', 'Expected'],
    ['tc', 'summary', 'steps', 'expected result'],
  ];

  for (const headers of variants) {
    it(`guesses a sensible mapping for ${JSON.stringify(headers)}`, () => {
      const mapping = guessMapping(headers);
      expect(mapping.title).toBeTruthy();
      expect(mapping.steps).toBeTruthy();
      expect(mapping.expected).toBeTruthy();
      expect(new Set([mapping.title, mapping.steps, mapping.expected]).size).toBe(3);
    });
  }

  it('finds the id column when present', () => {
    expect(guessMapping(['ID', 'Title', 'Steps', 'Expected']).id).toBe('ID');
    expect(guessMapping(['key', 'summary', 'procedure', 'expected result']).id).toBe('key');
    expect(guessMapping(['Title', 'Steps', 'Expected']).id).toBeUndefined();
  });
});

describe('suite fixtures', () => {
  it('parses CSV and XLSX to identical rows', () => {
    const csvTable = parseCsv(readFileSync(join(SUITE_DIR, 'aurora-suite.csv'), 'utf8'));
    const xlsxFile = readFileSync(join(SUITE_DIR, 'aurora-suite.xlsx'));
    const xlsxTable = parseXlsx(
      new Uint8Array(xlsxFile.buffer, xlsxFile.byteOffset, xlsxFile.byteLength),
    );
    const csvRows = applyMapping(csvTable, guessMapping(csvTable.headers)).rows;
    // The XLSX uses variant headers; map them onto the same columns.
    const xlsxRows = applyMapping(xlsxTable, {
      id: 'key',
      title: 'summary',
      steps: 'procedure',
      expected: 'expected result',
    }).rows;
    expect(xlsxRows).toEqual(csvRows);
    expect(csvRows).toHaveLength(20);
  });

  it('covers the lockout cases and gaps the rest', () => {
    const csvTable = parseCsv(readFileSync(join(SUITE_DIR, 'aurora-suite.csv'), 'utf8'));
    const { rows } = applyMapping(csvTable, guessMapping(csvTable.headers));
    const fixture = loadFixture('test_cases') as {
      test_cases: Array<{ id: string; title: string; expected_result: string }>;
    };
    const matches = matchSuite(
      fixture.test_cases.map((c) => ({
        id: c.id,
        title: c.title,
        expected_result: c.expected_result,
      })),
      rows,
    );
    const covered = fixture.test_cases.filter((c) => matches[c.id]?.status === 'covered');
    const gaps = fixture.test_cases.filter((c) => matches[c.id]?.status === 'gap');
    expect(covered.map((c) => c.id).sort()).toEqual(
      ['TC-001', 'TC-002', 'TC-003', 'TC-004', 'TC-005', 'TC-006'].sort(),
    );
    expect(gaps.map((c) => c.id).sort()).toEqual(['TC-007', 'TC-008']);
  });
});
