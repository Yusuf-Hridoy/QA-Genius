'use client';

import { useRef, useState } from 'react';
import { ImagePlus, Paperclip, X } from 'lucide-react';
import { DEVICE_TYPES, computeReproducibility } from '@/lib/generators/bug-report/derived';
import { PROVIDERS } from '@/lib/llm/providers';
import { useDefaultKey } from '@/components/shell/key-badge';
import {
  base64Bytes,
  isImageMime,
  keptChip,
  processImageFile,
  processLogFile,
  type LogKind,
} from '@/lib/bug/attachments';
import { FormField } from '@/components/ui/form-field';
import { Input, Textarea } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Pill } from '@/components/ui/pill';
import { Button } from '@/components/ui/button';
import { fieldInt, fieldValue, type FormProps } from './types';

type ImageAttachment = { mime: string; dataBase64: string };
type LogAttachment = { name: string; text: string; kind: LogKind };

function readAttachments(value: Record<string, unknown>): {
  image?: ImageAttachment;
  log?: LogAttachment;
} {
  const raw = value.attachments;
  if (!raw || typeof raw !== 'object') return {};
  const record = raw as Record<string, unknown>;
  const out: { image?: ImageAttachment; log?: LogAttachment } = {};
  const image = record.image as Record<string, unknown> | undefined;
  if (image && typeof image.mime === 'string' && typeof image.dataBase64 === 'string') {
    out.image = { mime: image.mime, dataBase64: image.dataBase64 };
  }
  const log = record.log as Record<string, unknown> | undefined;
  if (log && typeof log.name === 'string' && typeof log.text === 'string') {
    out.log = {
      name: log.name,
      text: log.text,
      kind: log.kind === 'har' || log.kind === 'json' ? log.kind : 'text',
    };
  }
  return out;
}

function formatKilobytes(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const VISION_MESSAGE =
  "This provider/model can't read images. Switch to Gemini, OpenAI or Anthropic, or remove the screenshot.";

export function BugReportForm({ value, errors, onField }: FormProps) {
  const rawBug = fieldValue(value, 'raw_bug');
  const deviceType = fieldValue(value, 'device_type', 'Not specified');
  const totalAttempts = fieldInt(value, 'total_attempts', 1);
  const successfulAttempts = fieldInt(value, 'successful_attempts', 0);
  const instructions = fieldValue(value, 'instructions');

  const computedRepro = computeReproducibility(totalAttempts, successfulAttempts);
  const allSuccessful = successfulAttempts === totalAttempts && totalAttempts > 0;

  const defaultKey = useDefaultKey();
  const visionSupported = !defaultKey || PROVIDERS[defaultKey.provider].supportsVision;
  const attachments = readAttachments(value);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [logTotal, setLogTotal] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const setAttachments = (next: { image?: ImageAttachment; log?: LogAttachment }) => {
    onField('attachments', Object.keys(next).length > 0 ? next : undefined);
  };

  const attachImage = async (file: File) => {
    setAttachError(null);
    try {
      const processed = await processImageFile(file);
      setAttachments({ ...attachments, image: processed });
    } catch (error) {
      setAttachError(error instanceof Error ? error.message : 'Could not read the image.');
    }
  };

  const attachLog = async (file: File) => {
    setAttachError(null);
    try {
      const processed = await processLogFile(file);
      setLogTotal(processed.totalChars);
      setAttachments({
        ...attachments,
        log: { name: processed.name, text: processed.text, kind: processed.kind },
      });
    } catch (error) {
      setAttachError(error instanceof Error ? error.message : 'Could not read the log file.');
    }
  };

  const attachFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    // One image and one log per report: images go to the screenshot slot,
    // everything else is tried as a log.
    for (const file of list) {
      if (isImageMime(file.type)) {
        if (!visionSupported) {
          setAttachError(VISION_MESSAGE);
          continue;
        }
        await attachImage(file);
      } else {
        await attachLog(file);
      }
    }
  };

  const pasteImage = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (!file) continue;
        if (!visionSupported) {
          setAttachError(VISION_MESSAGE);
          continue;
        }
        void attachImage(file);
      }
    }
  };

  const attachmentsError =
    errors['attachments.image'] ?? errors['attachments.log'] ?? errors.attachments;

  const numberField = (label: string, field: string, current: number, error?: string) => (
    <FormField label={label} error={error}>
      <Input
        type="number"
        min={field === 'total_attempts' ? 1 : 0}
        value={Number.isFinite(current) ? current : ''}
        onChange={(e) => onField(field, e.target.value === '' ? undefined : Number(e.target.value))}
      />
    </FormField>
  );

  return (
    <div className="flex flex-col gap-3 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
      <div className="flex flex-col gap-2">
        <span id="bug-attachments-label" className="text-[13px] font-medium">
          Evidence
        </span>
        <div
          role="button"
          tabIndex={0}
          aria-labelledby="bug-attachments-label"
          onClick={() => fileInput.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') fileInput.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void attachFiles(e.dataTransfer.files);
          }}
          data-testid="bug-attachments-dropzone"
          className={
            dragging
              ? 'rounded-[var(--qg-radius)] border border-accent bg-accent-soft px-3 py-4 text-center text-[13px] text-accent'
              : 'rounded-[var(--qg-radius)] border border-dashed border-border-strong px-3 py-4 text-center text-[13px] text-muted'
          }
        >
          Drop a screenshot or a log file
        </div>
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          accept=".png,.jpg,.jpeg,.webp,.txt,.log,.json,.har"
          aria-label="Attach a screenshot or a log file"
          onChange={(e) => {
            void attachFiles(e.target.files ?? []);
            e.target.value = '';
          }}
        />
        {!visionSupported ? (
          <p className="text-[12px] text-warn-fg" data-testid="bug-vision-warning">
            {VISION_MESSAGE}
          </p>
        ) : null}
        {attachments.image ? (
          <div
            className="flex items-center gap-3 rounded-[var(--qg-radius)] border border-border bg-card-2 p-2"
            data-testid="bug-image-preview"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:${attachments.image.mime};base64,${attachments.image.dataBase64}`}
              alt="Attached screenshot"
              className="h-16 w-16 shrink-0 rounded-[var(--qg-radius)] object-cover"
            />
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1 text-[13px] font-medium">
                <ImagePlus className="h-3.5 w-3.5" aria-hidden />
                Screenshot
              </p>
              <p className="font-mono text-[12px] text-muted">
                {formatKilobytes(base64Bytes(attachments.image.dataBase64))}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Remove screenshot"
              onClick={() => {
                setAttachments(attachments.log ? { log: attachments.log } : {});
              }}
            >
              <X className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        ) : null}
        {attachments.log ? (
          <div
            className="flex flex-col gap-1.5 rounded-[var(--qg-radius)] border border-border bg-card-2 p-2.5"
            data-testid="bug-log-preview"
          >
            <div className="flex items-center gap-2">
              <Paperclip className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <p className="min-w-0 flex-1 truncate font-mono text-[12px]">
                {attachments.log.name}
              </p>
              <Pill tone="neutral">
                {keptChip(logTotal ?? attachments.log.text.length, attachments.log.text.length)}
              </Pill>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove log"
                onClick={() => {
                  setLogTotal(null);
                  setAttachments(attachments.image ? { image: attachments.image } : {});
                }}
              >
                <X className="h-4 w-4" aria-hidden />
              </Button>
            </div>
            <pre className="overflow-x-auto font-mono text-[12px] leading-relaxed text-text-2">
              {attachments.log.text.split('\n').slice(0, 5).join('\n')}
              {attachments.log.text.split('\n').length > 5 ? '\n…' : ''}
            </pre>
          </div>
        ) : null}
        {(attachError ?? attachmentsError) ? (
          <p className="text-[12px] text-bad-fg" role="alert">
            {attachError ?? attachmentsError}
          </p>
        ) : null}
      </div>

      <FormField label="Raw Bug Notes" error={errors.raw_bug}>
        <Textarea
          value={rawBug}
          onChange={(e) => onField('raw_bug', e.target.value)}
          onPaste={pasteImage}
          placeholder="Checkout button does nothing on the second click in Safari, 3 of 5 attempts, cart total shows 0"
          rows={6}
          aria-invalid={Boolean(errors.raw_bug)}
        />
      </FormField>

      <FormField label="Device type">
        <Select value={deviceType} onChange={(e) => onField('device_type', e.target.value)}>
          {DEVICE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
      </FormField>

      <div className="grid grid-cols-2 gap-3">
        <FormField label="OS version (optional)" error={errors.os_version}>
          <Input
            value={fieldValue(value, 'os_version')}
            onChange={(e) => onField('os_version', e.target.value)}
            placeholder="Windows 11, iOS 17.2"
          />
        </FormField>
        <FormField label="Browser / app version (optional)" error={errors.browser_version}>
          <Input
            value={fieldValue(value, 'browser_version')}
            onChange={(e) => onField('browser_version', e.target.value)}
            placeholder="Chrome 131, app v2.4.0"
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <FormField label="Build / environment (optional)" error={errors.build_env}>
          <Input
            value={fieldValue(value, 'build_env')}
            onChange={(e) => onField('build_env', e.target.value)}
            placeholder="Staging, release 2026.09"
          />
        </FormField>
        <FormField label="URL (optional)" error={errors.bug_url}>
          <Input
            value={fieldValue(value, 'bug_url')}
            onChange={(e) => onField('bug_url', e.target.value)}
            placeholder="https://staging.aurora-shop.dev/checkout"
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {numberField('Total attempts', 'total_attempts', totalAttempts, errors.total_attempts)}
        {numberField(
          'Times reproduced',
          'successful_attempts',
          successfulAttempts,
          errors.successful_attempts,
        )}
      </div>
      <div className="flex flex-col gap-1">
        {computedRepro ? <Pill tone="info">{computedRepro}</Pill> : null}
        {allSuccessful ? (
          <p className="text-[12px] text-warn-fg">
            Successful attempts equals total attempts — this may not be a reproducible bug.
          </p>
        ) : null}
      </div>

      <FormField label="Additional instructions (optional)" error={errors.instructions}>
        <Textarea
          value={instructions}
          onChange={(e) => onField('instructions', e.target.value)}
          placeholder="e.g. Flag any PII in the notes before formatting"
          rows={2}
        />
      </FormField>
    </div>
  );
}
