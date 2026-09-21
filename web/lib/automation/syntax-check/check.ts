import type { CheckStatus, Diagnostic, FileReport, InputFile } from './types';
import {
  checkEmptyTestBody,
  checkHardcodedSleep,
  checkMissingImports,
  checkPageObjectImports,
  checkUnbalancedDelimiters,
  detectLanguage,
  exportedClasses,
} from './rules';

type TsModule = typeof import('typescript');

let cachedTs: TsModule | null = null;

/** Lazily import the TypeScript compiler (kept out of the main bundle). */
async function loadTypescript(): Promise<TsModule> {
  if (!cachedTs) cachedTs = await import('typescript');
  return cachedTs;
}

function toDiagnostic(
  ts: TsModule,
  file: string,
  code: string,
  d: import('typescript').Diagnostic,
): Diagnostic {
  let line = 1;
  let column = 1;
  if (d.file && typeof d.start === 'number') {
    const pos = d.file.getLineAndCharacterOfPosition(d.start);
    line = pos.line + 1;
    column = pos.character + 1;
  } else if (typeof d.start === 'number') {
    // No source file attached: fall back to an offset in the code.
    let seen = 0;
    for (let i = 0; i < Math.min(d.start, code.length); i += 1) {
      if (code[i] === '\n') {
        line += 1;
        column = 1;
      } else {
        column += 1;
      }
      seen = i;
    }
    void seen;
  }
  void file;
  return {
    line,
    column,
    message: ts.flattenDiagnosticMessageText(d.messageText, ' '),
    code: d.code,
  };
}

/**
 * Parse every TS/JS file with the TypeScript parser and apply the
 * deterministic structural rules. Python and other files are returned with
 * checked: false. Testable directly (no Worker involved).
 */
export async function checkFiles(
  files: InputFile[],
  options?: { framework?: string },
): Promise<FileReport[]> {
  const framework = options?.framework;
  const exportsByFile = new Map<string, string>();
  for (const file of files) {
    const language = detectLanguage(file.name);
    if (language !== 'ts' && language !== 'js') continue;
    for (const className of exportedClasses(file.code)) {
      if (!exportsByFile.has(className)) exportsByFile.set(className, file.name);
    }
  }

  const reports: FileReport[] = [];
  for (const file of files) {
    const language = detectLanguage(file.name);
    if (language !== 'ts' && language !== 'js') {
      reports.push({ name: file.name, language, errors: [], warnings: [], checked: false });
      continue;
    }
    const errors: Diagnostic[] = [];
    const warnings: Diagnostic[] = [];
    try {
      const ts = await loadTypescript();
      const result = ts.transpileModule(file.code, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ESNext,
          jsx: ts.JsxEmit.Preserve,
        },
        reportDiagnostics: true,
        fileName: file.name,
      });
      for (const d of result.diagnostics ?? []) {
        if (d.category !== ts.DiagnosticCategory.Error) continue;
        errors.push(toDiagnostic(ts, file.name, file.code, d));
      }
    } catch {
      errors.push(...checkUnbalancedDelimiters(file.code));
    }
    errors.push(...checkMissingImports(file.code, framework));
    errors.push(...checkPageObjectImports(file.name, file.code, exportsByFile));
    errors.push(...checkEmptyTestBody(file.code));
    warnings.push(...checkHardcodedSleep(file.code));
    reports.push({ name: file.name, language, errors, warnings, checked: true });
  }
  return reports;
}

/** Whole-result status from per-file reports (before any repair mapping). */
export function summarizeReports(reports: FileReport[]): CheckStatus {
  const checked = reports.filter((r) => r.checked);
  if (checked.length === 0) return 'unchecked';
  return checked.some((r) => r.errors.length > 0) ? 'errors' : 'clean';
}

/** Total error count across checked files. */
export function countErrors(reports: FileReport[]): number {
  return reports.filter((r) => r.checked).reduce((sum, r) => sum + r.errors.length, 0);
}

/** Total warning count across checked files. */
export function countWarnings(reports: FileReport[]): number {
  return reports.filter((r) => r.checked).reduce((sum, r) => sum + r.warnings.length, 0);
}
