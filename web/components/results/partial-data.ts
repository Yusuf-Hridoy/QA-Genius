/**
 * Safe accessors for partially-streamed result objects. Every array defaults
 * to [], every string to "" — renderers must never crash on undefined.
 */
export function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

export function num(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

export function arr<T = unknown>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

export function record(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}
