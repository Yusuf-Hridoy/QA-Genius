/**
 * No-raw-hex check (brief §15): fails if a raw #RRGGBB hex colour appears in
 * components or app TypeScript/TSX files. Tokens in globals.css are the only
 * source of colour; shiki themes and xlsx cell styles are generated data.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SCAN_DIRS = ['components', 'app'];
const HEX = /#[0-9A-Fa-f]{6}\b/;

const hits = [];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (!entry.startsWith('.')) yield* walk(full);
    } else {
      yield full;
    }
  }
}

for (const dir of SCAN_DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    if (!file.endsWith('.tsx') && !file.endsWith('.ts')) continue;
    const text = readFileSync(file, 'utf8');
    const lines = text.split('\n');
    lines.forEach((line, i) => {
      if (HEX.test(line)) {
        hits.push(`${relative(ROOT, file)}:${i + 1}: ${line.trim()}`);
      }
    });
  }
}

if (hits.length > 0) {
  console.error('Raw hex colours found (use the CSS tokens in globals.css):\n' + hits.join('\n'));
  process.exit(1);
}
console.log('check-hex: OK');
