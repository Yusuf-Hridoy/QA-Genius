import { describe, expect, it } from 'vitest';
import { GLOBAL_RULES } from '@/lib/prompts/global-rules';
import { buildStoryPrompt } from '@/lib/generators/story-analyzer/prompt';
import { buildTestCasesPrompt } from '@/lib/generators/test-cases/prompt';
import { buildBugReportPrompt } from '@/lib/generators/bug-report/prompt';
import { buildAutomationPrompt } from '@/lib/generators/automation-script/prompt';
import { StoryAnalyzerRequest } from '@/lib/generators/story-analyzer/request';
import { TestCasesRequest } from '@/lib/generators/test-cases/request';
import { BugReportRequest } from '@/lib/generators/bug-report/request';
import { buildStoryInterpretationPrompt } from '@/lib/duel/story-interpretation/prompt';
import { buildDuelComparePrompt } from '@/lib/duel/duel-compare/prompt';
import { StoryInterpretationRequest } from '@/lib/duel/story-interpretation/request';
import { AutomationRequest } from '@/lib/generators/automation-script/request';

describe('story analyzer prompt', () => {
  const req = StoryAnalyzerRequest.parse({
    user_story: 'As a shopper, I want to save items for later so I can buy them next visit.',
    story_type: 'User Story',
    project_context: 'Aurora Storefront',
  });

  it('system contains the global rules and a JSON schema block', () => {
    const { system } = buildStoryPrompt(req);
    expect(system).toContain(GLOBAL_RULES.trim().slice(0, 60));
    expect(system).toContain('Respond with ONLY a JSON object matching this JSON Schema:');
    expect(system).toContain('"ambiguity_score"');
  });

  it('assembles the user prompt verbatim from v1', () => {
    const { user } = buildStoryPrompt(req);
    expect(user).toBe(
      'Story Type: User Story\n' +
        'Project Context: Aurora Storefront\n\n' +
        'User Story / Requirement:\n' +
        req.user_story,
    );
  });

  it("uses 'Not provided' when context is empty", () => {
    const { user } = buildStoryPrompt({ ...req, project_context: undefined });
    expect(user).toContain('Project Context: Not provided');
  });

  it('appends instructions only when present', () => {
    expect(buildStoryPrompt(req).user).not.toContain('ADDITIONAL INSTRUCTIONS');
    const withInstructions = buildStoryPrompt({ ...req, instructions: 'Focus on security' });
    expect(withInstructions.user).toContain(
      '\n\nADDITIONAL INSTRUCTIONS FROM USER:\nFocus on security',
    );
  });
});

describe('test cases prompt', () => {
  const req = TestCasesRequest.parse({
    user_story: 'As a shopper, I want cart quantity limits so the warehouse can fulfil orders.',
    coverage_focus: ['Functional', 'Negative'],
    tech_stack: 'Next.js, Node API, Postgres',
  });

  it('assembles the user prompt verbatim from v1', () => {
    const { user } = buildTestCasesPrompt(req);
    expect(user).toBe(
      'User Story / Requirement:\n' +
        req.user_story +
        '\n\n' +
        'Test Coverage Focus: Functional, Negative\n' +
        'Tech Stack: Next.js, Node API, Postgres',
    );
  });

  it('system contains the global rules', () => {
    expect(buildTestCasesPrompt(req).system).toContain('GLOBAL RULES');
  });
});

describe('test cases pipeline appendices', () => {
  const base = TestCasesRequest.parse({
    user_story: 'As a shopper, I want cart quantity limits so the warehouse can fulfil orders.',
    coverage_focus: ['Functional', 'Negative'],
    tech_stack: 'Next.js, Node API, Postgres',
  });

  it('omits the criteria and previous blocks when absent', () => {
    const { user } = buildTestCasesPrompt(base);
    expect(user).not.toContain('Acceptance criteria');
    expect(user).not.toContain('Previous test cases');
  });

  it('appends the criteria block exactly', () => {
    const { user } = buildTestCasesPrompt({
      ...base,
      criteria: [
        { id: 'AC-1', text: 'Cart holds at most 10 units per SKU' },
        { id: 'AC-2', text: 'Over-limit quantities show a notice' },
      ],
    });
    expect(user).toContain(
      'Acceptance criteria (use these ids in the "traceability" field, e.g. "AC-2" or "AC-1, AC-3"):\n' +
        'AC-1: Cart holds at most 10 units per SKU\n' +
        'AC-2: Over-limit quantities show a notice',
    );
  });

  it('appends the previous block for the refine loop', () => {
    const { user } = buildTestCasesPrompt({
      ...base,
      previous: [{ id: 'TC-001', title: 'Happy path checkout' }],
      instructions: 'Make the negative cases stricter',
    });
    expect(user).toContain(
      'Previous test cases (revise; keep ids for cases you keep, reuse ids for changed cases, new ids for new cases):\n' +
        'TC-001 — Happy path checkout',
    );
    expect(user).toContain('ADDITIONAL INSTRUCTIONS FROM USER:\nMake the negative cases stricter');
  });
});

describe('bug report prompt', () => {
  const req = BugReportRequest.parse({
    raw_bug: 'Checkout button does nothing on the second click in Safari',
    device_type: 'Desktop',
    os_version: 'macOS 14.5',
    total_attempts: 5,
    successful_attempts: 2,
  });

  it('derives the reproducibility and environment strings', () => {
    const { user } = buildBugReportPrompt(req);
    expect(user).toContain('Reproducibility: Intermittent (2 of 5)');
    expect(user).toContain('Environment Details: Device: Desktop; OS: macOS 14.5');
    expect(user).toContain('Total Attempts: 5');
    expect(user).toContain('Successful Attempts: 2');
  });

  it('system contains the global rules', () => {
    expect(buildBugReportPrompt(req).system).toContain('GLOBAL RULES');
  });
});

describe('automation prompt', () => {
  const base = {
    scenario: 'Verify the login flow locks the account after five failed attempts.',
    structure: 'Page Object Model',
    browsers: ['Chromium'],
    site_type: 'Custom (paste URL above)',
  };

  it('keeps the requested language for JavaScript frameworks', () => {
    const req = AutomationRequest.parse({
      ...base,
      framework: 'Playwright (JavaScript)',
      language: 'TypeScript',
    });
    const { user } = buildAutomationPrompt(req);
    expect(user).toContain('Language: TypeScript');
    expect(user).toContain('Browsers: Chromium');
  });

  it('forces Python into the prompt variables for Python frameworks', () => {
    const req = AutomationRequest.parse({
      ...base,
      framework: 'Selenium (Python)',
      language: 'JavaScript',
    });
    const { user } = buildAutomationPrompt(req);
    expect(user).toContain('Language: Python');
  });
});

describe('duel prompts', () => {
  const story =
    'As a shopper, I want my account to lock after several failed login attempts so that my account stays secure.';

  function interpretationReq(persona: 'A' | 'B') {
    return StoryInterpretationRequest.parse({ user_story: story, persona });
  }

  it('personas A and B differ only in the intended line', () => {
    const a = buildStoryInterpretationPrompt(interpretationReq('A'));
    const b = buildStoryInterpretationPrompt(interpretationReq('B'));
    expect(a.system).toContain('strictest reading');
    expect(b.system).toContain('most permissive reading');
    expect(a.system.replace('strictest', 'X')).not.toBe(b.system.replace('most permissive', 'X'));
    expect(a.user).toBe(b.user.replace('Persona: B', 'Persona: A'));
  });

  it('tells the model to copy source phrases exactly', () => {
    const { system } = buildStoryInterpretationPrompt(interpretationReq('A'));
    expect(system).toContain('EXACTLY as it appears in the story text');
  });

  it('freezes the duel system prompts', () => {
    expect(buildStoryInterpretationPrompt(interpretationReq('A')).system).toMatchSnapshot();
    const compare = buildDuelComparePrompt({
      user_story: story,
      a: {
        actors: [],
        preconditions: [],
        rules: [],
        numbers: [],
        outcomes: [],
        assumptions: [],
      },
      b: {
        actors: [],
        preconditions: [],
        rules: [],
        numbers: [],
        outcomes: [],
        assumptions: [],
      },
    });
    expect(compare.system).toMatchSnapshot();
    expect(compare.user).toContain('Reading A:');
    expect(compare.user).toContain('Reading B:');
  });
});

describe('system prompt snapshots', () => {
  it("freezes each kind's system prompt", () => {
    const story = buildStoryPrompt(
      StoryAnalyzerRequest.parse({
        user_story: 'As a shopper, I want to save items for later so I can buy them next visit.',
      }),
    );
    const testCases = buildTestCasesPrompt(
      TestCasesRequest.parse({
        user_story: 'As a shopper, I want cart quantity limits so the warehouse can fulfil orders.',
      }),
    );
    const bug = buildBugReportPrompt(
      BugReportRequest.parse({ raw_bug: 'Checkout button does nothing in Safari' }),
    );
    const automation = buildAutomationPrompt(
      AutomationRequest.parse({
        scenario: 'Verify the login flow locks the account after five failed attempts.',
      }),
    );

    expect(story.system).toMatchSnapshot();
    expect(testCases.system).toMatchSnapshot();
    expect(bug.system).toMatchSnapshot();
    expect(automation.system).toMatchSnapshot();
  });
});
