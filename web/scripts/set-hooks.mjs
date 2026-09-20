/**
 * Points this repo's git hooks at web/.husky (monorepo layout: the Next.js app
 * lives in web/ while .git sits at the repo root). Idempotent — runs on
 * `pnpm install` via the `prepare` script.
 */
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const webDir = dirname(dirname(fileURLToPath(import.meta.url)));
const rootDir = resolve(webDir, '..');

execSync('git config core.hooksPath web/.husky', { cwd: rootDir, stdio: 'inherit' });
console.log('git hooks path set to web/.husky');
