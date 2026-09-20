import { z } from 'zod';

/** "Respond with ONLY a JSON object matching this JSON Schema:\n…" — replaces v1 {format_instructions}. */
export function formatInstructions(schema: z.ZodType): string {
  return `Respond with ONLY a JSON object matching this JSON Schema:\n${JSON.stringify(z.toJSONSchema(schema), null, 2)}`;
}

/** Appended to the user prompt when the request carries extra instructions. */
export function withInstructions(user: string, instructions?: string): string {
  if (!instructions) return user;
  return `${user}\n\nADDITIONAL INSTRUCTIONS FROM USER:\n${instructions}`;
}
