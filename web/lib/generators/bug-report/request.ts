import { z } from 'zod';
import { DEVICE_TYPES } from './derived';

export const BugReportRequest = z
  .object({
    raw_bug: z.string().trim().min(20).max(3000),
    device_type: z.enum(DEVICE_TYPES).default('Not specified'),
    os_version: z.string().trim().max(100).optional(),
    browser_version: z.string().trim().max(100).optional(),
    build_env: z.string().trim().max(100).optional(),
    bug_url: z.string().trim().max(500).optional(),
    total_attempts: z.number().int().min(1).default(1),
    successful_attempts: z.number().int().min(0).default(0),
    instructions: z.string().trim().max(1000).optional(),
    /**
     * Evidence attachments (Phase 3): one screenshot and/or one log excerpt.
     * Image bytes are excluded from the total-input cap and the
     * suspicious-content scan in generate.ts.
     */
    attachments: z
      .object({
        image: z
          .object({
            mime: z.enum(['image/jpeg', 'image/png', 'image/webp']),
            dataBase64: z.string().max(2_800_000),
          })
          .optional(),
        log: z
          .object({
            name: z.string().max(200),
            text: z.string().max(20_000),
            kind: z.enum(['text', 'json', 'har']),
          })
          .optional(),
      })
      .optional(),
  })
  .refine((v) => v.successful_attempts <= v.total_attempts, {
    path: ['successful_attempts'],
    message: 'Cannot exceed total attempts.',
  });

export type BugReportRequest = z.infer<typeof BugReportRequest>;
