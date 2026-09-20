'use client';

import type { ComponentType } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Bug, FileText, ListChecks, Terminal } from 'lucide-react';
import type { GeneratorKind } from '@/lib/generators/kinds';
import { StoryAnalyzerForm } from '@/components/forms/story-analyzer-form';
import { TestCasesForm } from '@/components/forms/test-cases-form';
import { BugReportForm } from '@/components/forms/bug-report-form';
import { AutomationForm } from '@/components/forms/automation-form';
import {
  StoryResult,
  TestCasesResult,
  BugReportResult,
  AutomationResult,
} from '@/components/results';
import {
  StoryExports,
  TestCasesExports,
  BugExports,
  AutomationExports,
} from '@/components/results/export-buttons';
import type { FormProps } from '@/components/forms/types';
import type { ExportsProps, ResultProps } from '@/components/results/types';
import storyExample from '@/fixtures/story_analyzer/input-1.json';
import testCasesExample from '@/fixtures/test_cases/input-1.json';
import bugReportExample from '@/fixtures/bug_report/input-1.json';
import automationExample from '@/fixtures/automation_script/input-1.json';

export type GeneratorUi = {
  Form: ComponentType<FormProps>;
  Result: ComponentType<ResultProps>;
  Exports: ComponentType<ExportsProps>;
  example: Record<string, unknown>;
  emptyIcon: LucideIcon;
  emptyHeadline: string;
  emptyDescription: string;
};

export const GENERATOR_UI: Record<GeneratorKind, GeneratorUi> = {
  story_analyzer: {
    Form: StoryAnalyzerForm,
    Result: StoryResult,
    Exports: StoryExports,
    example: storyExample as Record<string, unknown>,
    emptyIcon: FileText,
    emptyHeadline: 'Analyze a story',
    emptyDescription:
      'Paste a user story to score its clarity, check INVEST, and get acceptance criteria.',
  },
  test_cases: {
    Form: TestCasesForm,
    Result: TestCasesResult,
    Exports: TestCasesExports,
    example: testCasesExample as Record<string, unknown>,
    emptyIcon: ListChecks,
    emptyHeadline: 'Generate test cases',
    emptyDescription: 'Paste a story or requirement and choose the coverage you want.',
  },
  bug_report: {
    Form: BugReportForm,
    Result: BugReportResult,
    Exports: BugExports,
    example: bugReportExample as Record<string, unknown>,
    emptyIcon: Bug,
    emptyHeadline: 'Format a bug report',
    emptyDescription: 'Paste rough notes and optional environment details.',
  },
  automation_script: {
    Form: AutomationForm,
    Result: AutomationResult,
    Exports: AutomationExports,
    example: automationExample as Record<string, unknown>,
    emptyIcon: Terminal,
    emptyHeadline: 'Scaffold an automation project',
    emptyDescription: 'Describe the scenario and pick a framework, language, and structure.',
  },
  ping: {
    // Ping never renders as a screen; the settings page calls its API directly.
    Form: StoryAnalyzerForm,
    Result: StoryResult,
    Exports: StoryExports,
    example: {},
    emptyIcon: FileText,
    emptyHeadline: '',
    emptyDescription: '',
  },
};
