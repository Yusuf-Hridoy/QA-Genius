/**
 * Suspicious-content check, ported verbatim from v1 validators.detect_suspicious_content.
 * v2 does not block on a match — generate.ts sets x-qag-suspicious: 1 and continues.
 */
const INJECTION_PATTERNS: RegExp[] = [
  /ignore (previous|all|prior) instructions/,
  /disregard (the |your )?(system|previous) prompt/,
  /reveal (your |the )?(system prompt|instructions)/,
  /output (your |the )?(system prompt|instructions)/,
  /you are now (a |an )?(different|new)/,
  /forget everything/,
  /jailbreak/,
  /dan mode/,
];

export function detectSuspicious(text: string): boolean {
  const lower = text.toLowerCase();
  return INJECTION_PATTERNS.some((pattern) => pattern.test(lower));
}
