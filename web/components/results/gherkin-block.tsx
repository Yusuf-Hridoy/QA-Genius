'use client';

import { CopyButton } from '@/components/ui/copy-button';

const KEYWORDS = /^(Given|When|Then|And|But|Scenario:|Feature:)\b/;

/** Bold Given/When/Then/And/But keywords line by line — plain text, no shiki. */
function renderLine(line: string, index: number) {
  const match = KEYWORDS.exec(line.trim());
  if (!match) {
    return <div key={index}>{line || '\u00A0'}</div>;
  }
  const keyword = match[1] as string;
  const rest = line.trim().slice(keyword.length);
  const indent = line.match(/^\s*/)?.[0] ?? '';
  return (
    <div key={index}>
      {indent}
      <span className="font-semibold">{keyword}</span>
      {rest}
    </div>
  );
}

/**
 * Gherkin acceptance-criteria block: models escape newlines as the two-character
 * \n sequence inside strings, so they are unfolded before display.
 */
export function GherkinBlock({ code, title }: { code: string; title?: string }) {
  const text = code.replace(/\\n/g, '\n');
  return (
    <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-card-2">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="font-mono text-[12px] text-muted">{title ?? 'gherkin'}</span>
        <CopyButton text={text} />
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[12px] leading-[1.7] text-text-2">
        {text.split('\n').map(renderLine)}
      </pre>
    </div>
  );
}
