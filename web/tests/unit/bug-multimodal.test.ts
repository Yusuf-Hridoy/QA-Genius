import { beforeEach, describe, expect, it, vi } from 'vitest';

const { generateTextMock, streamObjectMock } = vi.hoisted(() => ({
  generateTextMock: vi.fn(),
  streamObjectMock: vi.fn(),
}));

vi.mock('ai', async (importOriginal) => {
  const actual = await importOriginal<typeof import('ai')>();
  return {
    ...actual,
    generateText: generateTextMock,
    streamObject: streamObjectMock,
  };
});

import type { ModelMessage } from 'ai';
import { generateStream } from '@/lib/llm/generate';
import { POST } from '@/app/api/generate/[kind]/route';
import { appendAttachmentText, buildUserMessages } from '@/lib/llm/multimodal';
import type { Byok } from '@/lib/llm/byok';

const byok: Byok = { provider: 'gemini', apiKey: 'test-key-123456789', tier: 'fast' };
const groqByok: Byok = { provider: 'groq', apiKey: 'test-key-123456789', tier: 'fast' };

const bugBody = {
  raw_bug:
    'Checkout button does nothing on the second click in Safari, reproduced 3 of 5 attempts on staging.',
};

const image = { mime: 'image/png', dataBase64: Buffer.from('fake-png-bytes').toString('base64') };

async function* textDeltas(chunks: string[]): AsyncGenerator<{ type: string; textDelta: string }> {
  for (const textDelta of chunks) yield { type: 'text-delta', textDelta };
}

beforeEach(() => {
  generateTextMock.mockReset();
  streamObjectMock.mockReset();
});

describe('attachment user text', () => {
  it('appends the log in the exact block format', () => {
    const user = appendAttachmentText('Raw bug notes:\nnotes', {
      log: { name: 'console.log', text: 'TypeError: x', kind: 'text' },
    });
    expect(user).toBe(
      'Raw bug notes:\nnotes\n\n' +
        'Attached log (console.log, text, last 12 characters):\n' +
        '```text\n' +
        'TypeError: x\n' +
        '```',
    );
  });

  it('appends the image grounding note and leaves plain prompts untouched', () => {
    const withImage = appendAttachmentText('notes', { image });
    expect(withImage).toBe(
      'notes\n\nAn annotated screenshot is attached. Ground "actual_result", ' +
        '"steps_to_reproduce" and "screenshot_annotations" in what is visible; ' +
        'do not invent UI elements that are not shown.',
    );
    expect(appendAttachmentText('notes', undefined)).toBe('notes');
    expect(appendAttachmentText('notes', {})).toBe('notes');
  });

  it('builds a user message with text and image parts', () => {
    const messages = buildUserMessages('prompt text', image);
    expect(messages).toHaveLength(1);
    const content = (messages[0] as { content: unknown[] }).content;
    expect(content[0]).toMatchObject({ type: 'text', text: 'prompt text' });
    const imagePart = content[1] as { type: string; image: Buffer; mediaType: string };
    expect(imagePart.type).toBe('image');
    expect(imagePart.mediaType).toBe('image/png');
    expect(Buffer.isBuffer(imagePart.image)).toBe(true);
  });
});

describe('multimodal generate path', () => {
  it('sends messages with an image part and keeps the system prompt', async () => {
    streamObjectMock.mockReturnValue({ fullStream: textDeltas(['{}']) });

    await generateStream({
      kind: 'bug_report',
      body: { ...bugBody, attachments: { image } },
      byok,
      requestId: 'req-vision',
    });

    expect(streamObjectMock).toHaveBeenCalledOnce();
    const args = streamObjectMock.mock.calls[0]?.[0] as {
      system: string;
      prompt?: string;
      messages?: ModelMessage[];
    };
    expect(args.prompt).toBeUndefined();
    expect(args.system).toContain('Bug Triage Specialist');
    expect(args.messages).toHaveLength(1);
    const content = (args.messages?.[0] as { content: Array<{ type: string; text?: string }> })
      .content;
    expect(content.map((part) => part.type)).toEqual(['text', 'image']);
    expect(content[0]?.text).toContain('An annotated screenshot is attached.');
  });

  it('uses the prompt path when no image is attached', async () => {
    streamObjectMock.mockReturnValue({ fullStream: textDeltas(['{}']) });

    await generateStream({
      kind: 'bug_report',
      body: {
        ...bugBody,
        attachments: { log: { name: 'c.log', text: 'boom', kind: 'text' } },
      },
      byok,
      requestId: 'req-log',
    });

    const args = streamObjectMock.mock.calls[0]?.[0] as {
      prompt?: string;
      messages?: ModelMessage[];
    };
    expect(args.messages).toBeUndefined();
    expect(args.prompt).toContain('Attached log (c.log, text, last 4 characters):');
  });

  it('rejects images on providers without vision support', async () => {
    const response = await POST(
      new Request('http://localhost/api/generate/bug_report', {
        method: 'POST',
        headers: { 'x-llm-provider': 'groq', 'x-llm-key': 'test-key-123456789' },
        body: JSON.stringify({ ...bugBody, attachments: { image } }),
      }),
      { params: Promise.resolve({ kind: 'bug_report' }) },
    );

    expect(response.status).toBe(400);
    const data = (await response.json()) as { error: string; message: string };
    expect(data.error).toBe('vision_unsupported');
    expect(data.message).toContain("can't read images");
    expect(streamObjectMock).not.toHaveBeenCalled();
    expect(groqByok.provider).toBe('groq');
  });
});
