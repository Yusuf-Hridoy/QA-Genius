'use client';

import { useEffect, useRef, useState } from 'react';
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
 * highlightLines marks 1-based lines (diagnostics navigation); the first
 * highlighted line is scrolled into view.
 */
export function CodeBlock({
  code,
  language,
  filename,
  className,
  highlightLines,
  scrollToLine,
}: {
  code: string;
  language: string;
  filename?: string;
  className?: string;
  highlightLines?: number[];
  scrollToLine?: number;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const highlightKey = (highlightLines ?? []).join(',');
  const targetLine = scrollToLine ?? highlightLines?.[0];

  useEffect(() => {
    let cancelled = false;
    const highlight = highlightKey
      .split(',')
      .map((n) => Number(n))
      .filter((n) => Number.isFinite(n) && n > 0);
    codeToHtml(code, {
      lang: langFor(language),
      theme: 'github-light-default',
      transformers: [
        {
          name: 'qag-line-highlight',
          line(node, line) {
            // shiki keeps the line class in a `class` string prop; fold it
            // into className so the highlight merges into ONE class attribute
            // (a second attribute would be dropped by the HTML parser).
            const prev = { ...(node.properties ?? {}) } as Record<string, unknown>;
            const fromClass =
              typeof prev.class === 'string' ? prev.class.split(/\s+/).filter(Boolean) : [];
            const fromClassName = Array.isArray(prev.className)
              ? prev.className.map(String)
              : typeof prev.className === 'string'
                ? [prev.className]
                : [];
            const className = [...fromClass, ...fromClassName];
            if (highlight.includes(line)) className.push('qag-highlight-line');
            delete prev.class;
            node.properties = { ...prev, className, dataQagLine: line };
          },
        },
      ],
    })
      .then((result) => {
        if (!cancelled) setHtml(result);
      })
      .catch(() => {
        if (!cancelled) setHtml(null);
      });
    return () => {
      cancelled = true;
    };
  }, [code, language, highlightKey]);

  // Scroll the highlighted line into view once the HTML is rendered.
  useEffect(() => {
    if (html === null || targetLine === undefined) return;
    const el = bodyRef.current?.querySelector(`[data-qag-line="${targetLine}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [html, targetLine]);

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
          ref={bodyRef}
          className="overflow-x-auto p-3 [&_code]:block [&_code]:font-mono [&_code]:text-[12px] [&_code]:leading-relaxed [&_pre]:m-0 [&_pre]:bg-transparent"
          // shiki output is static generated code, not user input
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="overflow-x-auto p-3 font-mono text-[12px] leading-relaxed">
          <code>
            {code.split('\n').map((line, i) => {
              const lineNumber = i + 1;
              const highlighted = (highlightLines ?? []).includes(lineNumber);
              return (
                <span
                  key={lineNumber}
                  data-qag-line={lineNumber}
                  ref={
                    lineNumber === targetLine
                      ? (el) => {
                          el?.scrollIntoView({ block: 'nearest' });
                        }
                      : undefined
                  }
                  className={highlighted ? 'qag-highlight-line' : undefined}
                >
                  {line}
                  {'\n'}
                </span>
              );
            })}
          </code>
        </pre>
      )}
    </div>
  );
}
