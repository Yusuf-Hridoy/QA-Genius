import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import type { BugReport } from '@/lib/generators/bug-report/schema';
import { dateStamp, downloadText } from './download';

/** Story analysis Markdown — sections mirror the result UI order. */
export function storyToMarkdown(analysis: AmbiguityAnalysis): string {
  const lines: string[] = [];
  lines.push('# Story analysis');
  lines.push('');
  lines.push(`Ambiguity ${analysis.ambiguity_score}/100 · ${analysis.clarity_label}`);
  lines.push('');
  lines.push('## INVEST');
  lines.push('');
  const invest: [string, string][] = [
    ['Independent', analysis.invest_independent],
    ['Negotiable', analysis.invest_negotiable],
    ['Valuable', analysis.invest_valuable],
    ['Estimable', analysis.invest_estimable],
    ['Small', analysis.invest_small],
    ['Testable', analysis.invest_testable],
  ];
  for (const [label, value] of invest) {
    lines.push(`- **${label}**: ${value}`);
  }
  lines.push(`- **Overall**: ${analysis.invest_overall}`);
  lines.push('');

  lines.push('## Vague phrases');
  lines.push('');
  for (const vp of analysis.vague_phrases) {
    lines.push(`- "${vp.phrase}" (${vp.severity}) — ${vp.suggestion}`);
    lines.push(`  - Replacement: ${vp.replacement}`);
  }
  lines.push('');

  lines.push('## Missing elements');
  lines.push('');
  for (const item of analysis.missing_elements) lines.push(`- ${item}`);
  lines.push('');

  lines.push('## Risks');
  lines.push('');
  for (const risk of analysis.risks) lines.push(`- ${risk}`);
  lines.push('');

  lines.push('## Suggested rewrites');
  lines.push('');
  analysis.suggested_rewrites.forEach((rewrite, i) => lines.push(`${i + 1}. ${rewrite}`));
  lines.push('');

  lines.push('## Acceptance criteria');
  lines.push('');
  for (const ac of analysis.generated_acceptance_criteria) {
    lines.push('```gherkin');
    lines.push(ac.replace(/\\n/g, '\n'));
    lines.push('```');
    lines.push('');
  }

  if (analysis.recommended_split && analysis.recommended_split.length > 0) {
    lines.push('## Recommended split');
    lines.push('');
    for (const story of analysis.recommended_split) lines.push(`- ${story}`);
    lines.push('');
  }

  if (analysis.score_breakdown) {
    lines.push('## How the score was computed');
    lines.push('');
    lines.push('```');
    lines.push(analysis.score_breakdown);
    lines.push('```');
    lines.push('');
  }

  return lines.join('\n');
}

export function downloadStoryMarkdown(analysis: AmbiguityAnalysis, slug: string) {
  downloadText(
    `${slug}-story-analysis-${dateStamp()}.md`,
    storyToMarkdown(analysis),
    'text/markdown',
  );
}

/** Bug report Markdown — also what "Copy as Markdown" copies. */
export function bugToMarkdown(bug: BugReport): string {
  const lines: string[] = [];
  lines.push(`# ${bug.title}`);
  lines.push('');
  lines.push('| Field | Value |');
  lines.push('|-------|-------|');
  lines.push(`| **Severity** | ${bug.severity} |`);
  lines.push(`| **Reproducibility** | ${bug.reproducibility_rate} |`);
  lines.push(`| **Root Cause** | ${bug.root_cause_category ?? 'N/A'} |`);
  lines.push(`| **Regression Risk** | ${bug.regression_risk ?? 'N/A'} |`);
  lines.push(`| **Affected Users** | ${bug.affected_users ?? 'N/A'} |`);
  lines.push('');
  lines.push('## Business Impact');
  lines.push('');
  lines.push(bug.business_impact ?? 'N/A');
  lines.push('');
  lines.push('## Environment');
  lines.push('');
  lines.push('```');
  lines.push(bug.environment_details);
  lines.push('```');
  lines.push('');
  lines.push('## Steps to Reproduce');
  lines.push('');
  bug.steps_to_reproduce.forEach((step, i) => lines.push(`${i + 1}. ${step}`));
  lines.push('');
  lines.push('## Actual Result');
  lines.push('');
  lines.push(bug.actual_result);
  lines.push('');
  lines.push('## Expected Result');
  lines.push('');
  lines.push(bug.expected_result);
  lines.push('');

  const optional: [string, string | string[] | undefined][] = [
    ['Suspected Pattern', bug.suspected_pattern],
    ['Suggested Fix', bug.suggested_fix],
    ['Workaround', bug.workaround],
    ['Related Areas', bug.related_areas],
    ['Jira Labels', bug.jira_labels],
    ['Investigation Steps', bug.investigation_steps],
    ['Related Issues', bug.related_issues],
    ['Screenshot Annotations', bug.screenshot_annotations],
  ];
  for (const [heading, value] of optional) {
    if (!value || (Array.isArray(value) && value.length === 0)) continue;
    lines.push(`## ${heading}`);
    lines.push('');
    if (Array.isArray(value)) {
      value.forEach((item, i) => lines.push(`${i + 1}. ${item}`));
    } else {
      lines.push(value);
    }
    lines.push('');
  }

  return lines.join('\n');
}

export function downloadBugMarkdown(bug: BugReport, slug: string) {
  downloadText(`${slug}-bug-report-${dateStamp()}.md`, bugToMarkdown(bug), 'text/markdown');
}
