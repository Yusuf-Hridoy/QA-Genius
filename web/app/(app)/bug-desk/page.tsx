'use client';

import { GeneratorScreen } from '@/components/generators/generator-screen';
import { usePageInfo } from '@/components/shell/shell-context';

export default function BugDeskPage() {
  usePageInfo({ workspace: 'Bug desk' });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-[22px] font-semibold">Bug desk</h1>
      <GeneratorScreen kind="bug_report" />
    </div>
  );
}
