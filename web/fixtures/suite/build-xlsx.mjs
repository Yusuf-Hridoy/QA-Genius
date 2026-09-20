import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const Papa = require('papaparse');
const XLSX = require('xlsx-js-style');

const dir = dirname(fileURLToPath(import.meta.url));
const csvText = readFileSync(join(dir, 'aurora-suite.csv'), 'utf8');
// Variant header names on purpose: the mapping guesser must still find them.
const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });
const rows = parsed.data.map((r) => [r.ID, r.Title, r.Steps, r['Expected Result']]);
const sheet = XLSX.utils.aoa_to_sheet([
  ['key', 'summary', 'procedure', 'expected result'],
  ...rows,
]);
sheet['!cols'] = [{ wch: 10 }, { wch: 60 }, { wch: 60 }, { wch: 60 }];
const workbook = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(workbook, sheet, 'Suite');
XLSX.writeFile(workbook, join(dir, 'aurora-suite.xlsx'));
console.info(`wrote aurora-suite.xlsx with ${rows.length} rows`);
