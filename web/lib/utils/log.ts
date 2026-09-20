/**
 * The only logger in the app. ESLint forbids console.* outside this file.
 * Never pass raw API keys here — log request ids, kinds, and error names only.
 */
export const log = {
  info(message: string): void {
    console.info(`[qag] ${message}`);
  },
  warn(message: string): void {
    console.warn(`[qag] ${message}`);
  },
  error(message: string, error?: unknown): void {
    const name = error instanceof Error ? error.name : typeof error;
    console.error(`[qag] ${message} (${name})`);
  },
};
