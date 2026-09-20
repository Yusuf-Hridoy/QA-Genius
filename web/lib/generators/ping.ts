import { z } from 'zod';
import type { Tier } from '@/lib/llm/providers';

/** Internal health-check kind (brief §6.5). Not listed in /api/generators. */
export const PingRequest = z.object({});

export const PingOutput = z.object({
  ok: z.literal(true),
});

export const PING_PROMPT = {
  system: 'You are a health check. Reply with JSON only.',
  user: 'Return {"ok": true}',
} as const;

export type PingRequest = z.infer<typeof PingRequest>;
export type PingOutput = z.infer<typeof PingOutput>;
export type { Tier };
