import { AttachmentTooLargeError } from '@/lib/llm/errors';

/** Separate JSON body cap for attachment-carrying requests (brief §2.2). */
export const MAX_JSON_BODY_BYTES = 3 * 1024 * 1024;

/**
 * Read a JSON request body with a pre-check on content-length plus a streamed
 * read guard, so oversized attachment payloads fail with 413 before the LLM
 * layer ever sees them. Unparseable bodies keep the historical {} fallback.
 */
export async function readJsonBody(req: Request): Promise<unknown> {
  const declared = req.headers.get('content-length');
  if (declared !== null && Number(declared) > MAX_JSON_BODY_BYTES) {
    throw new AttachmentTooLargeError();
  }
  if (!req.body) {
    const text = await req.text();
    if (new TextEncoder().encode(text).length > MAX_JSON_BODY_BYTES) {
      throw new AttachmentTooLargeError();
    }
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return {};
    }
  }
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_JSON_BODY_BYTES) {
      await reader.cancel().catch(() => {});
      throw new AttachmentTooLargeError();
    }
    chunks.push(value);
  }
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder().decode(merged)) as unknown;
  } catch {
    return {};
  }
}
