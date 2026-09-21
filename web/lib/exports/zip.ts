import JSZip from 'jszip';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';
import type { SyntaxSummary } from '@/lib/automation/syntax-store';
import { dateStamp, downloadBlob, downloadText } from './download';

/** All project files as [filename, content] pairs. */
export function automationFiles(script: AutomationScript): [string, string][] {
  const files: [string, string][] = [];
  if (script.page_object_file_name && script.page_object_code) {
    files.push([script.page_object_file_name, script.page_object_code]);
  }
  files.push([script.test_file_name, script.test_code]);
  if (script.conftest_file_name && script.conftest_code) {
    files.push([script.conftest_file_name, script.conftest_code]);
  }
  if (script.config_file_name && script.config_code) {
    files.push([script.config_file_name, script.config_code]);
  }
  if (script.requirements_txt) {
    files.push(['requirements.txt', script.requirements_txt]);
  }
  return files;
}

function readmeFor(script: AutomationScript): string {
  const lines = [`# ${script.framework} automation project`, ''];
  lines.push('## Setup');
  lines.push('');
  script.setup_instructions.forEach((step, i) => lines.push(`${i + 1}. ${step}`));
  lines.push('');
  lines.push('## Run');
  lines.push('');
  lines.push('```sh');
  lines.push(script.execution_command);
  lines.push('```');
  if (script.design_notes) {
    lines.push('');
    lines.push('## Design notes');
    lines.push('');
    lines.push(script.design_notes);
  }
  lines.push('');
  return lines.join('\n');
}

/** ZIP of all project files plus a generated README.md. */
export async function downloadAutomationZip(
  script: AutomationScript,
  slug: string,
  syntax?: SyntaxSummary,
) {
  const zip = new JSZip();
  for (const [name, content] of automationFiles(script)) {
    zip.file(name, content);
  }
  zip.file('README.md', readmeFor(script));
  if (syntax && (syntax.afterErrors > 0 || syntax.warnings > 0 || syntax.beforeErrors > 0)) {
    zip.file('SYNTAX-CHECK.md', syntaxCheckMarkdown(syntax));
  }
  const blob = await zip.generateAsync({ type: 'blob' });
  downloadBlob(`${slug}-automation-${dateStamp()}.zip`, blob);
}

/** Honest syntax-check summary: parser-based, not a full type check. */
export function syntaxCheckMarkdown(syntax: SyntaxSummary): string {
  const lines = ['# Syntax check', ''];
  const statusLine =
    syntax.badge.status === 'clean'
      ? `syntax clean${syntax.warnings > 0 ? ` · ${syntax.warnings} warning${syntax.warnings === 1 ? '' : 's'}` : ''}`
      : syntax.badge.status === 'repaired'
        ? `repaired · was ${syntax.beforeErrors} error${syntax.beforeErrors === 1 ? '' : 's'}`
        : syntax.badge.status === 'errors'
          ? `${syntax.afterErrors} error${syntax.afterErrors === 1 ? '' : 's'} remain`
          : 'not checked';
  lines.push(`Status: ${statusLine}`);
  lines.push('');
  lines.push(
    'Checked with the TypeScript parser plus structural rules (imports, empty tests, hardcoded sleeps). This is a syntax check, not a full type check.',
  );
  lines.push('');
  for (const report of syntax.reports) {
    if (!report.checked) {
      lines.push(`## ${report.name} — not checked`);
      lines.push('');
      continue;
    }
    const total = report.errors.length + report.warnings.length;
    lines.push(
      `## ${report.name} — ${report.errors.length} error${report.errors.length === 1 ? '' : 's'}${report.warnings.length > 0 ? `, ${report.warnings.length} warning${report.warnings.length === 1 ? '' : 's'}` : ''}${total === 0 ? ' — clean' : ''}`,
    );
    lines.push('');
    for (const error of report.errors) {
      lines.push(`- ${error.line}:${error.column} — ${error.message}`);
    }
    for (const warning of report.warnings) {
      lines.push(`- ${warning.line}:${warning.column} (warning) — ${warning.message}`);
    }
    if (total > 0) lines.push('');
  }
  return lines.join('\n');
}

/** Download a SYNTAX-CHECK.md summary alongside a single file. */
export function downloadSyntaxSummary(syntax: SyntaxSummary, slug: string) {
  downloadText(
    `${slug}-SYNTAX-CHECK-${dateStamp()}.md`,
    syntaxCheckMarkdown(syntax),
    'text/markdown',
  );
}

/** Download a single source file (e.g. the test file). */
export function downloadSourceFile(filename: string, content: string, slug: string) {
  const base = filename.split('/').pop() ?? filename;
  downloadText(`${slug}-${base}`, content, 'text/plain');
}
