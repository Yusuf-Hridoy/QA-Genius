export type FormProps = {
  value: Record<string, unknown>;
  errors: Record<string, string>;
  onField: (field: string, value: unknown) => void;
};

/** Read a string field from loosely-typed form state. */
export function fieldValue(value: Record<string, unknown>, field: string, fallback = ''): string {
  const v = value[field];
  return typeof v === 'string' ? v : fallback;
}

/** Read a string-array field from loosely-typed form state. */
export function fieldArray(value: Record<string, unknown>, field: string): string[] {
  const v = value[field];
  return Array.isArray(v) ? v.filter((item): item is string => typeof item === 'string') : [];
}

/** Read an integer field from loosely-typed form state. */
export function fieldInt(value: Record<string, unknown>, field: string, fallback: number): number {
  const v = value[field];
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
