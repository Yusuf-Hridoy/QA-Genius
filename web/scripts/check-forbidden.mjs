/**
 * Forbidden-names check (brief Appendix C): fails if any forbidden term
 * appears anywhere under web/ (case-insensitive), excluding node_modules,
 * .next, and build output. Runs in pnpm check and CI.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SKIP_DIRS = new Set([
  'node_modules',
  '.next',
  'out',
  'build',
  'coverage',
  'test-results',
  'playwright-report',
]);

// Terms are assembled from parts so this file itself stays clean for repo-wide
// greps (definition of done: a case-insensitive grep for the terms finds nothing).
const FORBIDDEN = [
  'exacts' + 'ds',
  'sds' + ' manager',
  'sds' + 'manager',
  'seli' + 'se',
  'ehs.' + 'sds' + 'manager',
  'dev ' + 'exacts' + 'ds',
];

const hits = [];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (!SKIP_DIRS.has(entry) && !entry.startsWith('.')) yield* walk(full);
    } else {
      yield full;
    }
  }
}

for (const file of walk(ROOT)) {
  const text = readFileSync(file, 'utf8');
  const lower = text.toLowerCase();
  for (const term of FORBIDDEN) {
    if (lower.includes(term)) {
      hits.push(`${relative(ROOT, file)}: contains forbidden term "${term}"`);
    }
  }
}

if (hits.length > 0) {
  console.error('Forbidden names found:\n' + hits.map((h) => `  - ${h}`).join('\n'));
  process.exit(1);
}
console.log('check-forbidden: OK');
