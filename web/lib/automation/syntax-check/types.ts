/** Types for the Automation syntax check (Phase 3.1). */

export type Language = 'ts' | 'js' | 'python' | 'other';

export type Diagnostic = {
  line: number;
  column: number;
  message: string;
  code?: string | number;
};

export type FileReport = {
  name: string;
  language: Language;
  errors: Diagnostic[];
  warnings: Diagnostic[];
  /** False for Python and non-code files: not checked in this phase. */
  checked: boolean;
};

export type InputFile = { name: string; code: string };

/** Whole-result status: repaired is set by the repair loop, not the checker. */
export type CheckStatus = 'clean' | 'errors' | 'unchecked';
