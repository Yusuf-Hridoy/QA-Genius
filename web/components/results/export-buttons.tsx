'use client';

import {
  Download,
  FileArchive,
  FileCode2,
  FileDown,
  FileSpreadsheet,
  FileText,
} from 'lucide-react';
import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import type { TestCaseList } from '@/lib/generators/test-cases/schema';
import type { BugReport } from '@/lib/generators/bug-report/schema';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';
import { downloadJson } from '@/lib/exports/json';
import { downloadStoryMarkdown } from '@/lib/exports/markdown';
import { downloadTestCasesCsv } from '@/lib/exports/csv';
import { downloadTestCasesXlsx } from '@/lib/exports/xlsx';
import { downloadFeature } from '@/lib/exports/feature';
import { bugToMarkdown, downloadBugMarkdown } from '@/lib/exports/markdown';
import { downloadAutomationZip, downloadSourceFile } from '@/lib/exports/zip';
import { projectSlug } from '@/lib/exports/download';
import { useProjectStore } from '@/lib/store/project';
import { copyWithToast } from '@/components/ui/copy-button';
import { Button } from '@/components/ui/button';
import type { ExportsProps } from './types';

function useSlug(): string {
  const name = useProjectStore((s) => s.project.name);
  return projectSlug(name);
}

function ExportBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted">Export</span>
      {children}
    </div>
  );
}

export function StoryExports({ data }: ExportsProps) {
  const slug = useSlug();
  const analysis = data as unknown as AmbiguityAnalysis;
  return (
    <ExportBar>
      <Button variant="secondary" onClick={() => downloadStoryMarkdown(analysis, slug)}>
        <FileText className="h-3.5 w-3.5" aria-hidden />
        Markdown
      </Button>
      <Button variant="secondary" onClick={() => downloadJson(data, 'story-analysis', slug)}>
        <FileDown className="h-3.5 w-3.5" aria-hidden />
        JSON
      </Button>
    </ExportBar>
  );
}

export function TestCasesExports({ data, input }: ExportsProps) {
  const slug = useSlug();
  const result = data as unknown as TestCaseList;
  const storyTitle =
    typeof input.user_story === 'string' ? input.user_story : 'Generated test cases';
  return (
    <ExportBar>
      <Button variant="secondary" onClick={() => downloadTestCasesCsv(result, slug)}>
        <FileText className="h-3.5 w-3.5" aria-hidden />
        CSV
      </Button>
      <Button variant="secondary" onClick={() => downloadTestCasesXlsx(result, slug)}>
        <FileSpreadsheet className="h-3.5 w-3.5" aria-hidden />
        XLSX
      </Button>
      <Button variant="secondary" onClick={() => downloadFeature(result, storyTitle, slug)}>
        <FileCode2 className="h-3.5 w-3.5" aria-hidden />
        .feature
      </Button>
      <Button variant="secondary" onClick={() => downloadJson(data, 'test-cases', slug)}>
        <FileDown className="h-3.5 w-3.5" aria-hidden />
        JSON
      </Button>
    </ExportBar>
  );
}

export function BugExports({ data }: ExportsProps) {
  const slug = useSlug();
  const bug = data as unknown as BugReport;
  return (
    <ExportBar>
      <Button
        variant="secondary"
        onClick={() => void copyWithToast(bugToMarkdown(bug), 'Markdown copied')}
      >
        <FileText className="h-3.5 w-3.5" aria-hidden />
        Copy as Markdown
      </Button>
      <Button variant="secondary" onClick={() => downloadBugMarkdown(bug, slug)}>
        <Download className="h-3.5 w-3.5" aria-hidden />
        Download Markdown
      </Button>
      <Button variant="secondary" onClick={() => downloadJson(data, 'bug-report', slug)}>
        <FileDown className="h-3.5 w-3.5" aria-hidden />
        JSON
      </Button>
    </ExportBar>
  );
}

export function AutomationExports({ data }: ExportsProps) {
  const slug = useSlug();
  const script = data as unknown as AutomationScript;
  return (
    <ExportBar>
      <Button variant="secondary" onClick={() => void downloadAutomationZip(script, slug)}>
        <FileArchive className="h-3.5 w-3.5" aria-hidden />
        ZIP project
      </Button>
      <Button
        variant="secondary"
        onClick={() => downloadSourceFile(script.test_file_name, script.test_code, slug)}
      >
        <FileCode2 className="h-3.5 w-3.5" aria-hidden />
        Test file
      </Button>
      <Button variant="secondary" onClick={() => downloadJson(data, 'automation', slug)}>
        <FileDown className="h-3.5 w-3.5" aria-hidden />
        JSON
      </Button>
    </ExportBar>
  );
}
