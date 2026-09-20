'use client';

import { useEffect, useState } from 'react';
import { codeToHtml } from 'shiki';
import { cn } from '@/lib/utils/cn';
import { CopyButton } from './copy-button';

const EXT_TO_LANG: Record<string, string> = {
  ts: 'ts',
  js: 'js',
  json: 'json',
  py: 'python',
  feature: 'text',
  txt: 'text',
  md: 'text',
  ini: 'ini',
};

function langFor(language: string): string {
  const lower = language.toLowerCase();
  if (lower === 'gherkin' || lower === 'feature') return 'text';
  return EXT_TO_LANG[lower] ?? lower;
}

/**
 * Mono 12px code block with shiki highlighting (light theme to match look D)
 * and a copy button top-right. Gherkin is rendered as plain text elsewhere.
 */
export function CodeBlock({
  code,
  language,
  filename,
  className,
}: {
  code: string;
  language: string;
  filename?: string;
  className?: string;
}) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    codeToHtml(code, { lang: langFor(language), theme: 'github-light-default' })
      .then((result) => {
        if (!cancelled) setHtml(result);
      })
      .catch(() => {
        if (!cancelled) setHtml(null);
      });
    return () => {
      cancelled = true;
    };
  }, [code, language]);

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[var(--qg-radius)] border border-border bg-card-2',
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="font-mono text-[12px] text-muted">{filename ?? language}</span>
        <CopyButton text={code} />
      </div>
      {html ? (
        <div
          className="overflow-x-auto p-3 [&_code]:block [&_code]:font-mono [&_code]:text-[12px] [&_code]:leading-relaxed [&_pre]:m-0 [&_pre]:bg-transparent"
          // shiki output is static generated code, not user input
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="overflow-x-auto p-3 font-mono text-[12px] leading-relaxed">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
