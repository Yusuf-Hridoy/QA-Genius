import { z } from 'zod';
import { deflateSync, inflateSync, strFromU8, strToU8 } from 'fflate';
import type { Run } from '@/lib/pipeline/types';

/** Share payload envelope. Versioned; unknown versions are rejected. */
export const SharePayload = z.object({
  v: z.literal(1),
  kind: z.literal('run'),
  run: z.unknown(),
  project: z.object({ name: z.string(), stack: z.string() }),
});

export type SharePayload = z.infer<typeof SharePayload>;

export const WARN_BYTES = 64 * 1024;
export const MAX_BYTES = 200 * 1024;

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlToBytes(fragment: string): Uint8Array {
  const base64 = fragment.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  let binary: string;
  try {
    binary = atob(padded);
  } catch {
    throw new ShareDecodeError('The share link could not be read.');
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export class ShareDecodeError extends Error {}

/** Strip per-request meta (provider, model, latency): never shared. */
export function stripRunForShare(run: Run): Record<string, unknown> {
  const clone = JSON.parse(JSON.stringify(run)) as Record<string, unknown>;
  const story = clone.story as Record<string, unknown> | undefined;
  if (story) delete story.meta;
  const testCases = clone.testCases as Record<string, unknown> | undefined;
  if (testCases) delete testCases.meta;
  return clone;
}

/** JSON → deflate → base64url. The fragment never touches the server. */
export function encodeShare(run: Run, project: { name: string; stack: string }): string {
  const payload = { v: 1, kind: 'run', run: stripRunForShare(run), project };
  return bytesToBase64Url(deflateSync(strToU8(JSON.stringify(payload))));
}

/** Inverse of encodeShare. Throws ShareDecodeError on any invalid input. */
export function decodeShare(fragment: string): SharePayload {
  if (!fragment) throw new ShareDecodeError('The share link is empty.');
  let json: string;
  try {
    json = strFromU8(inflateSync(base64UrlToBytes(fragment)));
  } catch {
    throw new ShareDecodeError('The share link could not be read.');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new ShareDecodeError('The share link could not be read.');
  }
  const result = SharePayload.safeParse(parsed);
  if (!result.success) {
    throw new ShareDecodeError('This share link uses an unsupported format.');
  }
  return result.data;
}

/** Byte size of the encoded fragment (for the size line and caps). */
export function fragmentBytes(fragment: string): number {
  return new TextEncoder().encode(fragment).length;
}

export function formatKilobytes(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
