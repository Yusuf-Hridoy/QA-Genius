import JSZip from 'jszip';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';
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
export async function downloadAutomationZip(script: AutomationScript, slug: string) {
  const zip = new JSZip();
  for (const [name, content] of automationFiles(script)) {
    zip.file(name, content);
  }
  zip.file('README.md', readmeFor(script));
  const blob = await zip.generateAsync({ type: 'blob' });
  downloadBlob(`${slug}-automation-${dateStamp()}.zip`, blob);
}

/** Download a single source file (e.g. the test file). */
export function downloadSourceFile(filename: string, content: string, slug: string) {
  const base = filename.split('/').pop() ?? filename;
  downloadText(`${slug}-${base}`, content, 'text/plain');
}
