'use client';

import { checkFiles } from './check';
import type { FileReport, InputFile } from './types';
import type { CheckRequestMessage, CheckResponseMessage } from './worker';

let sequence = 0;

const CHECK_TIMEOUT_MS = 30_000;

/**
 * Run the syntax check in a Web Worker (the TypeScript compiler chunk loads
 * lazily, only when Automation output is checked). Falls back to an inline
 * check when Workers are unavailable.
 */
export function runSyntaxCheck(files: InputFile[], framework?: string): Promise<FileReport[]> {
  try {
    const worker = new Worker(new URL('./worker.ts', import.meta.url));
    return new Promise<FileReport[]>((resolve, reject) => {
      const id = (sequence += 1);
      const timeout = setTimeout(() => {
        worker.terminate();
        reject(new Error('Syntax check timed out.'));
      }, CHECK_TIMEOUT_MS);
      worker.onmessage = (e: MessageEvent<CheckResponseMessage>) => {
        if (e.data.id !== id) return;
        clearTimeout(timeout);
        worker.terminate();
        resolve(e.data.reports);
      };
      worker.onerror = (e: ErrorEvent) => {
        clearTimeout(timeout);
        worker.terminate();
        reject(e.error instanceof Error ? e.error : new Error('Syntax check failed.'));
      };
      const message: CheckRequestMessage = { id, files, framework };
      worker.postMessage(message);
    });
  } catch {
    return checkFiles(files, { framework });
  }
}
