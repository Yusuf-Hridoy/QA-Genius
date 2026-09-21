import type { ModelMessage } from 'ai';

export type EvidenceImage = { mime: string; dataBase64: string };
export type EvidenceLog = { name: string; text: string; kind: string };
export type EvidenceAttachments = { image?: EvidenceImage; log?: EvidenceLog };

const IMAGE_NOTE =
  'An annotated screenshot is attached. Ground "actual_result", "steps_to_reproduce" ' +
  'and "screenshot_annotations" in what is visible; do not invent UI elements that are not shown.';

/**
 * Append evidence to the user prompt (user prompt only; system prompts are
 * verbatim and snapshot-tested). Exact block formats are pinned by unit tests.
 */
export function appendAttachmentText(user: string, attachments?: EvidenceAttachments): string {
  let next = user;
  const log = attachments?.log;
  if (log && log.text.length > 0) {
    next +=
      `\n\nAttached log (${log.name}, ${log.kind}, last ${log.text.length} characters):\n` +
      '```text\n' +
      `${log.text}\n` +
      '```';
  }
  if (attachments?.image) {
    next += `\n\n${IMAGE_NOTE}`;
  }
  return next;
}

/** User message carrying the prompt text plus the screenshot for vision models. */
export function buildUserMessages(userText: string, image: EvidenceImage): ModelMessage[] {
  return [
    {
      role: 'user',
      content: [
        { type: 'text', text: userText },
        {
          type: 'image',
          image: Buffer.from(image.dataBase64, 'base64'),
          mediaType: image.mime,
        },
      ],
    },
  ];
}

/** Append a trailing text instruction to user messages (fallback/re-ask paths). */
export function appendMessageText(messages: ModelMessage[], text: string): ModelMessage[] {
  return [...messages, { role: 'user', content: [{ type: 'text', text }] }];
}
