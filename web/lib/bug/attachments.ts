/**
 * Client-side attachment processing for the Bug desk (Phase 3.2).
 * One screenshot and/or one console/network log per report. All caps are
 * enforced here and again by the request schema + route body guard.
 */

export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
export const MAX_LOG_BYTES = 2 * 1024 * 1024;
export const MAX_IMAGE_SIDE = 1600;
export const MAX_LOG_CHARS = 20_000;
export const MAX_HAR_LINES = 200;
export const PNG_KEEP_BYTES = 1 * 1024 * 1024;

export const IMAGE_MIMES = ['image/png', 'image/jpeg', 'image/webp'] as const;
export type ImageMime = (typeof IMAGE_MIMES)[number];

export type ProcessedImage = {
  mime: ImageMime;
  /** Raw base64 (no data: prefix), ready for the request schema. */
  dataBase64: string;
  /** Binary size after downscaling, for the thumbnail label. */
  sizeBytes: number;
};

export type LogKind = 'text' | 'json' | 'har';

export type ProcessedLog = {
  name: string;
  text: string;
  kind: LogKind;
  /** Source characters before the tail cut, for the kept-count chip. */
  totalChars: number;
  /** First lines for the preview. */
  preview: string[];
};

export function isImageMime(mime: string): mime is ImageMime {
  return (IMAGE_MIMES as readonly string[]).includes(mime);
}

export function validateImageFile(file: File): string | null {
  if (!isImageMime(file.type)) {
    return 'Screenshots must be PNG, JPEG, or WebP.';
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return 'Screenshots must be 8 MB or smaller.';
  }
  return null;
}

const LOG_EXTENSIONS = ['.txt', '.log', '.json', '.har'] as const;

export function logKindFor(name: string): LogKind | null {
  const lower = name.toLowerCase();
  if (lower.endsWith('.har')) return 'har';
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.txt') || lower.endsWith('.log')) return 'text';
  return null;
}

export function validateLogFile(file: File): string | null {
  if (logKindFor(file.name) === null) {
    return `Logs must be one of ${LOG_EXTENSIONS.join(', ')}.`;
  }
  if (file.size > MAX_LOG_BYTES) {
    return 'Logs must be 2 MB or smaller.';
  }
  return null;
}

/** Binary size of a base64 payload (no prefix). */
export function base64Bytes(base64: string): number {
  return Math.floor(base64.length * 0.75);
}

function canvasHasTransparency(canvas: HTMLCanvasElement): boolean {
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return false;
  const { width, height } = canvas;
  const step = Math.max(1, Math.floor(Math.min(width, height) / 200));
  const image = context.getImageData(0, 0, width, height).data;
  for (let y = 0; y < height; y += step) {
    for (let x = 0; x < width; x += step) {
      if ((image[(y * width + x) * 4 + 3] as number) < 255) return true;
    }
  }
  return false;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = reader.result as string;
      resolve(url.slice(url.indexOf(',') + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error('Could not read the image.'));
    reader.readAsDataURL(blob);
  });
}

/**
 * Downscale so the longest side is ≤ 1600 px and encode as JPEG 0.85 —
 * except small PNGs with real transparency, which stay PNG.
 */
export async function processImageFile(file: File): Promise<ProcessedImage> {
  const error = validateImageFile(file);
  if (error) throw new Error(error);
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Could not read the image.');
    context.drawImage(bitmap, 0, 0, width, height);
    const keepPng =
      file.type === 'image/png' && file.size < PNG_KEEP_BYTES && canvasHasTransparency(canvas);
    const mime: ImageMime = keepPng ? 'image/png' : 'image/jpeg';
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, mime, 0.85));
    if (!blob) throw new Error('Could not read the image.');
    const dataBase64 = await blobToBase64(blob);
    return { mime, dataBase64, sizeBytes: blob.size };
  } finally {
    bitmap.close();
  }
}

/**
 * Extract failing network entries from a HAR object:
 * `METHOD URL → STATUS (ms)` lines for responses ≥ 400 or entries with
 * `_error` set, capped at 200 lines.
 */
export function extractHarErrors(harText: string): string {
  let har: unknown;
  try {
    har = JSON.parse(harText);
  } catch {
    throw new Error('The HAR file could not be read.');
  }
  const entries = (har as { log?: { entries?: unknown[] } })?.log?.entries;
  if (!Array.isArray(entries)) throw new Error('The HAR file has no log entries.');
  const lines: string[] = [];
  for (const entry of entries) {
    const candidate = entry as {
      request?: { method?: string; url?: string };
      response?: { status?: number };
      time?: number;
      _error?: unknown;
    };
    const status = candidate.response?.status;
    const failed =
      (typeof status === 'number' && status >= 400) ||
      (candidate._error !== undefined && candidate._error !== null);
    if (!failed) continue;
    const method = candidate.request?.method ?? 'GET';
    const url = candidate.request?.url ?? 'unknown url';
    const statusText = typeof status === 'number' ? String(status) : 'error';
    const ms = typeof candidate.time === 'number' ? ` (${Math.round(candidate.time)} ms)` : '';
    lines.push(`${method} ${url} → ${statusText}${ms}`);
    if (lines.length >= MAX_HAR_LINES) break;
  }
  return lines.join('\n');
}

/** Keep the last 20 000 characters — logs matter at the end. */
export function tailLog(text: string): { text: string; totalChars: number } {
  return { text: text.slice(-MAX_LOG_CHARS), totalChars: text.length };
}

export async function processLogFile(file: File): Promise<ProcessedLog> {
  const error = validateLogFile(file);
  if (error) throw new Error(error);
  const source = await file.text();
  const detected = logKindFor(file.name) ?? 'text';
  let kind: LogKind = detected;
  let relevant = source;
  if (detected === 'har') {
    try {
      relevant = extractHarErrors(source);
    } catch {
      // Unparseable HAR: fall back to the raw tail as plain text.
      kind = 'text';
      relevant = source;
    }
  }
  const { text } = tailLog(relevant);
  return {
    name: file.name.slice(0, 200),
    text,
    kind,
    totalChars: source.length,
    preview: relevant.split('\n').slice(0, 5),
  };
}

/** "20 000 of 84 312 chars kept" chip text. */
export function keptChip(totalChars: number, keptChars: number): string {
  return `${keptChars.toLocaleString('en-US')} of ${totalChars.toLocaleString('en-US')} chars kept`;
}
