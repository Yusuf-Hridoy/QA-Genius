import type { Diagnostic, Language } from './types';

/** File extension → language. Python and anything non-JS are not checked. */
export function detectLanguage(name: string): Language {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  if (ext === 'ts' || ext === 'tsx' || ext === 'mts' || ext === 'cts') return 'ts';
  if (ext === 'js' || ext === 'jsx' || ext === 'mjs' || ext === 'cjs') return 'js';
  if (ext === 'py') return 'python';
  return 'other';
}

export function isCypressFramework(framework?: string): boolean {
  return (framework ?? '').toLowerCase().includes('cypress');
}

/** Line/column (1-based) of a string index. */
export function lineColAt(code: string, index: number): { line: number; column: number } {
  let line = 1;
  let column = 1;
  for (let i = 0; i < index; i += 1) {
    if (code[i] === '\n') {
      line += 1;
      column = 1;
    } else {
      column += 1;
    }
  }
  return { line, column };
}

/**
 * Strip comments and string/template literals (replaced with spaces, newlines
 * preserved) so identifier scans do not flag words inside prose.
 */
export function stripCommentsAndStrings(code: string): string {
  let out = '';
  let i = 0;
  const n = code.length;
  while (i < n) {
    const ch = code[i] as string;
    const next = code[i + 1] as string;
    // Line comment.
    if (ch === '/' && next === '/') {
      while (i < n && code[i] !== '\n') {
        out += ' ';
        i += 1;
      }
      continue;
    }
    // Block comment.
    if (ch === '/' && next === '*') {
      out += '  ';
      i += 2;
      while (i < n && !(code[i] === '*' && code[i + 1] === '/')) {
        out += code[i] === '\n' ? '\n' : ' ';
        i += 1;
      }
      out += '  ';
      i += 2;
      continue;
    }
    // String or template literal.
    if (ch === "'" || ch === '"' || ch === '`') {
      const quote = ch;
      out += ' ';
      i += 1;
      while (i < n) {
        const c = code[i] as string;
        if (c === '\\') {
          out += '  ';
          i += 2;
          continue;
        }
        if (c === '\n' && quote !== '`') break;
        if (c === quote) {
          out += ' ';
          i += 1;
          break;
        }
        // ${...} inside template literals is code — stop stripping there.
        if (quote === '`' && c === '$' && code[i + 1] === '{') break;
        out += c === '\n' ? '\n' : ' ';
        i += 1;
      }
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

/** Identifiers that must be imported or declared before use in TS/JS output. */
const KNOWN_IDENTIFIERS = [
  'test',
  'expect',
  'Page',
  'Locator',
  'defineConfig',
  'devices',
  'cy',
  'describe',
  'it',
] as const;

/** Cypress provides these as globals; every other framework must import them. */
const CYPRESS_GLOBALS = new Set(['cy', 'describe', 'it']);

function isDeclared(stripped: string, ident: string): boolean {
  // import { ident } / import ident / const { a, ident } = require(...)
  if (new RegExp(`import\\s+(?:[^;]*?\\b${ident}\\b)`).test(stripped)) return true;
  if (new RegExp(`require\\s*\\([^)]*\\)`).test(stripped)) {
    // Destructured require: const { test, expect } = require('...').
    if (new RegExp(`(?:const|let|var)\\s+\\{[^}]*\\b${ident}\\b[^}]*\\}\\s*=`).test(stripped))
      return true;
  }
  // Local declaration: const/let/var/function/class/interface/type/enum.
  if (
    new RegExp(`(?:const|let|var|function|class|interface|type|enum)\\s+${ident}\\b`).test(stripped)
  )
    return true;
  // Function parameter: (..., ident, ...) — approximate.
  if (new RegExp(`\\(\\s*[^)]*\\b${ident}\\b[^)]*\\)\\s*(?:=>|\\{)`).test(stripped)) return true;
  return false;
}

function isUsed(stripped: string, ident: string): boolean {
  // Property access (page.test, test.describe) does not count as a bare use.
  // Import/require lines declare rather than use; check them separately.
  const withoutImports = stripped
    .split('\n')
    .filter((line) => !/^\s*import\b/.test(line) && !/require\s*\(/.test(line))
    .join('\n');
  return new RegExp(`(?<!\\.)\\b${ident}\\b`).test(withoutImports);
}

/**
 * Flag known test identifiers used without an import or declaration.
 * Cypress globals are exempt when the framework is Cypress.
 */
export function checkMissingImports(code: string, framework?: string): Diagnostic[] {
  const stripped = stripCommentsAndStrings(code);
  const diagnostics: Diagnostic[] = [];
  for (const ident of KNOWN_IDENTIFIERS) {
    if (isCypressFramework(framework) && CYPRESS_GLOBALS.has(ident)) continue;
    if (!isUsed(stripped, ident)) continue;
    if (isDeclared(stripped, ident)) continue;
    const match = new RegExp(`(?<!\\.)\\b${ident}\\b`).exec(stripped);
    const { line, column } = lineColAt(code, match?.index ?? 0);
    diagnostics.push({
      line,
      column,
      message: `“${ident}” is used but not imported or declared.`,
      code: 'missing-import',
    });
  }
  return diagnostics;
}

/** Exported class names of a file (for the page-object cross-file check). */
export function exportedClasses(code: string): string[] {
  const stripped = stripCommentsAndStrings(code);
  const names: string[] = [];
  const pattern = /export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(stripped)) !== null) {
    names.push(match[1] as string);
  }
  return names;
}

function isSpecFile(name: string): boolean {
  const lower = name.toLowerCase();
  return (
    lower.includes('spec') ||
    lower.includes('test') ||
    lower.includes('cy') ||
    lower.endsWith('.js')
  );
}

/**
 * A spec that references a class exported by another project file must import
 * it. `exportsByFile` maps class name → exporting file name.
 */
export function checkPageObjectImports(
  name: string,
  code: string,
  exportsByFile: Map<string, string>,
): Diagnostic[] {
  if (!isSpecFile(name)) return [];
  const stripped = stripCommentsAndStrings(code);
  const diagnostics: Diagnostic[] = [];
  for (const [className, exporter] of exportsByFile) {
    if (exporter === name) continue;
    if (!new RegExp(`(?<!\\.)\\b${className}\\b`).test(stripped)) continue;
    if (new RegExp(`import\\s+(?:[^;]*?\\b${className}\\b)`).test(stripped)) continue;
    const match = new RegExp(`(?<!\\.)\\b${className}\\b`).exec(stripped);
    const { line, column } = lineColAt(code, match?.index ?? 0);
    diagnostics.push({
      line,
      column,
      message: `“${className}” is used but not imported (exported by ${exporter}).`,
      code: 'page-object-not-imported',
    });
  }
  return diagnostics;
}

/** test(/it( callbacks with an empty body. Runs on stripped code (string
 *  contents are blanked), so the test name is matched as non-comma text. */
export function checkEmptyTestBody(code: string): Diagnostic[] {
  const stripped = stripCommentsAndStrings(code);
  const pattern = /(?:test|it)\s*\([^,]*,\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{\s*\}\s*\)/g;
  const diagnostics: Diagnostic[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(stripped)) !== null) {
    const { line, column } = lineColAt(code, match.index);
    diagnostics.push({ line, column, message: 'Empty test body.', code: 'empty-test-body' });
  }
  return diagnostics;
}

/** Hardcoded sleeps are warnings: they never block the syntax clean badge. */
export function checkHardcodedSleep(code: string): Diagnostic[] {
  const stripped = stripCommentsAndStrings(code);
  const diagnostics: Diagnostic[] = [];
  const patterns = [/waitForTimeout\s*\(/g, /cy\.wait\(\s*\d/g];
  for (const pattern of patterns) {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(stripped)) !== null) {
      const { line, column } = lineColAt(code, match.index);
      diagnostics.push({
        line,
        column,
        message: 'Hardcoded sleep makes tests flaky; prefer an explicit wait.',
        code: 'hardcoded-sleep',
      });
    }
  }
  return diagnostics;
}

/**
 * Fallback when the TypeScript parser throws instead of reporting
 * diagnostics: a comment/string-aware delimiter balance check.
 */
export function checkUnbalancedDelimiters(code: string): Diagnostic[] {
  const stripped = stripCommentsAndStrings(code);
  const pairs: Record<string, string> = { '{': '}', '(': ')', '[': ']' };
  const stack: { ch: string; index: number }[] = [];
  for (let i = 0; i < stripped.length; i += 1) {
    const ch = stripped[i] as string;
    if (ch in pairs) {
      stack.push({ ch, index: i });
      continue;
    }
    if (ch === '}' || ch === ')' || ch === ']') {
      const top = stack.pop();
      if (!top || pairs[top.ch] !== ch) {
        const { line, column } = lineColAt(code, i);
        return [
          {
            line,
            column,
            message: `Unbalanced delimiter “${ch}”.`,
            code: 'unbalanced-delimiters',
          },
        ];
      }
    }
  }
  if (stack.length > 0) {
    const first = stack[0] as { ch: string; index: number };
    const { line, column } = lineColAt(code, first.index);
    return [
      {
        line,
        column,
        message: `Unbalanced delimiter “${first.ch}” (never closed).`,
        code: 'unbalanced-delimiters',
      },
    ];
  }
  return [];
}
