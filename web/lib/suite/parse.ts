import Papa from 'papaparse';
import * as XLSX from 'xlsx-js-style';

export type SuiteRow = { id: string; title: string; steps: string; expected: string };

export type ColumnMapping = {
  id?: string;
  title: string;
  steps: string;
  expected: string;
};

export type RawTable = { headers: string[]; records: Array<Record<string, string>> };

/** Imports larger than this are truncated with a clear message. */
export const MAX_SUITE_ROWS = 5000;

const ID_PATTERN = /^(id|key|tc|test.?id|case.?id)$/;
const TITLE_PATTERN = /title|name|summary|test.?case/;
const STEPS_PATTERN = /steps?|procedure|actions?|description/;
const EXPECTED_PATTERN = /expected|result/;

function firstMatch(headers: string[], pattern: RegExp, used: Set<string>): string | undefined {
  const found = headers.find((h) => !used.has(h) && pattern.test(h.toLowerCase().trim()));
  if (found) used.add(found);
  return found;
}

/**
 * Guess the title/steps/expected (and optional id) columns from header
 * names. Callers fall back to positional columns when nothing matches.
 */
export function guessMapping(headers: string[]): ColumnMapping {
  const used = new Set<string>();
  const id = firstMatch(headers, ID_PATTERN, used);
  const title = firstMatch(headers, TITLE_PATTERN, used) ?? headers[0] ?? '';
  used.add(title);
  const steps = firstMatch(headers, STEPS_PATTERN, used) ?? headers[1] ?? '';
  used.add(steps);
  const expected = firstMatch(headers, EXPECTED_PATTERN, used) ?? headers[2] ?? '';
  return { ...(id ? { id } : {}), title, steps, expected };
}

function stringifyCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

export function parseCsv(text: string): RawTable {
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true,
  });
  if (parsed.errors.length > 0 && !parsed.meta.fields) {
    throw new Error('The CSV file could not be parsed.');
  }
  const headers = (parsed.meta.fields ?? []).map((h) => h.trim()).filter((h) => h.length > 0);
  if (headers.length === 0) throw new Error('The CSV file has no header row.');
  return { headers, records: parsed.data };
}

export function parseXlsx(buffer: ArrayBuffer | Uint8Array): RawTable {
  // Uint8Array: the bundler build of the reader misparses raw ArrayBuffers.
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  const workbook = XLSX.read(bytes, { type: 'array' });
  const firstSheet = workbook.SheetNames[0];
  if (!firstSheet) throw new Error('The workbook has no sheets.');
  const sheet = workbook.Sheets[firstSheet];
  if (!sheet) throw new Error('The workbook has no sheets.');
  const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, defval: '' });
  if (rows.length === 0) throw new Error('The sheet is empty.');
  const headers = (rows[0] as unknown[]).map(stringifyCell).map((h) => h.trim());
  if (headers.every((h) => h.length === 0)) throw new Error('The sheet has no header row.');
  const records = rows.slice(1).map((row) => {
    const record: Record<string, string> = {};
    (row as unknown[]).forEach((cell, i) => {
      const header = headers[i];
      if (header) record[header] = stringifyCell(cell);
    });
    return record;
  });
  return { headers: headers.filter((h) => h.length > 0), records };
}

/** Apply the column mapping; missing ids become positional `Row n` labels. */
export function applyMapping(
  table: RawTable,
  mapping: ColumnMapping,
): { rows: SuiteRow[]; truncated: boolean } {
  const sliced = table.records.slice(0, MAX_SUITE_ROWS);
  const rows = sliced.map((record, i) => ({
    id: mapping.id ? record[mapping.id]?.trim() || `Row ${i + 1}` : `Row ${i + 1}`,
    title: (record[mapping.title] ?? '').trim(),
    steps: (record[mapping.steps] ?? '').trim(),
    expected: (record[mapping.expected] ?? '').trim(),
  }));
  return { rows, truncated: table.records.length > MAX_SUITE_ROWS };
}
