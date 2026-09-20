/**
 * CSS token check (Phase 2.1): fails if globals.css reintroduces the shadcn
 * variable collision. All look D tokens are namespaced `--qg-*`; shadcn's own
 * names (`--card`, `--muted`, `--accent`, `--border`, `--ring`, `--radius`,
 * …) are aliases that must point at `--qg-*`.
 *
 * Rules (scoped to `:root` blocks):
 * 1. No custom property may reference itself (`--x: var(--x)` — invalid at
 *    computed-value time, silently kills the declaration).
 * 2. No non-`--qg-` custom property may be declared twice (later wins).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const CSS_PATH = fileURLToPath(new URL('../app/globals.css', import.meta.url));

function rootBlocks(css) {
  const blocks = [];
  const re = /:root\s*\{/g;
  let match;
  while ((match = re.exec(css)) !== null) {
    let depth = 1;
    let i = match.index + match[0].length;
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth += 1;
      if (css[i] === '}') depth -= 1;
      i += 1;
    }
    blocks.push(css.slice(match.index + match[0].length, i - 1));
  }
  return blocks;
}

const DECL = /(--[a-zA-Z0-9-_]+)\s*:\s*([^;{}]+);/g;

function varRefs(value, name) {
  // Exact-name references only: var(--radius) must not match var(--radius-card).
  const re = new RegExp(`var\\(\\s*${name.replace(/[-\]]/g, '\\$&')}\\s*[,)]`, 'g');
  return re.test(value);
}

const css = readFileSync(CSS_PATH, 'utf8');
const hits = [];
const seen = new Map();

for (const block of rootBlocks(css)) {
  for (const decl of block.matchAll(DECL)) {
    const [, name, value] = decl;
    if (varRefs(value, name)) {
      hits.push(`${name} references itself`);
    }
    if (!name.startsWith('--qg-')) {
      seen.set(name, (seen.get(name) ?? 0) + 1);
      if (seen.get(name) === 2) {
        hits.push(`${name} declared twice in :root`);
      }
    }
  }
}

if (hits.length > 0) {
  console.error('CSS token collision in globals.css:\n' + hits.map((h) => `  - ${h}`).join('\n'));
  process.exit(1);
}
console.log('check-css-tokens: OK');
