import type { z } from 'zod';
import type { Tier } from '@/lib/llm/providers';
import { AmbiguityAnalysis } from './story-analyzer/schema';
import { StoryAnalyzerRequest } from './story-analyzer/request';
import { buildStoryPrompt } from './story-analyzer/prompt';
import { TestCaseList } from './test-cases/schema';
import { TestCasesRequest } from './test-cases/request';
import { buildTestCasesPrompt } from './test-cases/prompt';
import { BugReport } from './bug-report/schema';
import { BugReportRequest } from './bug-report/request';
import { buildBugReportPrompt } from './bug-report/prompt';
import { AutomationScript } from './automation-script/schema';
import { AutomationRequest } from './automation-script/request';
import { buildAutomationPrompt } from './automation-script/prompt';
import { StoryInterpretation } from '@/lib/duel/story-interpretation/schema';
import { StoryInterpretationRequest } from '@/lib/duel/story-interpretation/request';
import { buildStoryInterpretationPrompt } from '@/lib/duel/story-interpretation/prompt';
import { DuelCompareOutput, DuelCompareRequest } from '@/lib/duel/duel-compare/schema';
import { buildDuelComparePrompt } from '@/lib/duel/duel-compare/prompt';
import { PingOutput, PingRequest, PING_PROMPT } from './ping';

export const GENERATOR_KINDS = [
  'story_analyzer',
  'test_cases',
  'bug_report',
  'automation_script',
  'story_interpretation',
  'duel_compare',
  'ping',
] as const;

export type GeneratorKind = (typeof GENERATOR_KINDS)[number];

export type GeneratorDef<Req, Out> = {
  kind: GeneratorKind;
  title: string;
  description: string;
  tier: Tier;
  internal?: boolean;
  /** Sampling temperature; defaults to 0.3 when omitted. */
  temperature?: number;
  requestSchema: z.ZodType<Req>;
  outputSchema: z.ZodType<Out>;
  buildPrompt(req: Req): { system: string; user: string };
};

type Registry = {
  story_analyzer: GeneratorDef<StoryAnalyzerRequest, AmbiguityAnalysis>;
  test_cases: GeneratorDef<TestCasesRequest, TestCaseList>;
  bug_report: GeneratorDef<BugReportRequest, BugReport>;
  automation_script: GeneratorDef<AutomationRequest, AutomationScript>;
  story_interpretation: GeneratorDef<StoryInterpretationRequest, StoryInterpretation>;
  duel_compare: GeneratorDef<DuelCompareRequest, DuelCompareOutput>;
  ping: GeneratorDef<PingRequest, PingOutput>;
};

export const REGISTRY: Registry = {
  story_analyzer: {
    kind: 'story_analyzer',
    title: 'Story analyzer',
    description: "Score a story's clarity, check INVEST, and get acceptance criteria.",
    tier: 'fast',
    requestSchema: StoryAnalyzerRequest,
    outputSchema: AmbiguityAnalysis,
    buildPrompt: buildStoryPrompt,
  },
  test_cases: {
    kind: 'test_cases',
    title: 'Test cases',
    description: 'Generate a categorized, prioritized test suite from a story or requirement.',
    tier: 'fast',
    requestSchema: TestCasesRequest,
    outputSchema: TestCaseList,
    buildPrompt: buildTestCasesPrompt,
  },
  bug_report: {
    kind: 'bug_report',
    title: 'Bug report',
    description: 'Format rough bug notes into a production-ready bug report.',
    tier: 'fast',
    requestSchema: BugReportRequest,
    outputSchema: BugReport,
    buildPrompt: buildBugReportPrompt,
  },
  automation_script: {
    kind: 'automation_script',
    title: 'Automation',
    description: 'Scaffold a runnable automation project for a test scenario.',
    tier: 'reasoning',
    requestSchema: AutomationRequest,
    outputSchema: AutomationScript,
    buildPrompt: buildAutomationPrompt,
  },
  story_interpretation: {
    kind: 'story_interpretation',
    title: 'Story interpretation',
    description: 'Internal: one committed reading for the Ambiguity Duel.',
    tier: 'fast',
    internal: true,
    temperature: 0.8,
    requestSchema: StoryInterpretationRequest,
    outputSchema: StoryInterpretation,
    buildPrompt: buildStoryInterpretationPrompt,
  },
  duel_compare: {
    kind: 'duel_compare',
    title: 'Duel comparison',
    description: 'Internal: diff two readings into forks and agreements.',
    tier: 'fast',
    internal: true,
    temperature: 0.2,
    requestSchema: DuelCompareRequest,
    outputSchema: DuelCompareOutput,
    buildPrompt: buildDuelComparePrompt,
  },
  ping: {
    kind: 'ping',
    title: 'Health check',
    description: 'Internal connectivity test.',
    tier: 'fast',
    internal: true,
    requestSchema: PingRequest,
    outputSchema: PingOutput,
    buildPrompt: () => ({ system: PING_PROMPT.system, user: PING_PROMPT.user }),
  },
};

export function isGeneratorKind(kind: string): kind is GeneratorKind {
  return (GENERATOR_KINDS as readonly string[]).includes(kind);
}

/** Non-internal kinds, for /api/generators and any UI listing. */
export const PUBLIC_KINDS = GENERATOR_KINDS.filter((k) => !REGISTRY[k].internal);
