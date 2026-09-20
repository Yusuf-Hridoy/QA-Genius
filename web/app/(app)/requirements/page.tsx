'use client';

import { useState } from 'react';
import { GeneratorScreen } from '@/components/generators/generator-screen';
import { Tabs } from '@/components/ui/tabs';
import { usePageInfo } from '@/components/shell/shell-context';
import type { GeneratorKind } from '@/lib/generators/kinds';

const TABS = [
  { value: 'story_analyzer', label: 'Story analyzer' },
  { value: 'test_cases', label: 'Test cases' },
  { value: 'automation_script', label: 'Automation' },
] as const;

export default function RequirementsPage() {
  const [tab, setTab] = useState<string>('story_analyzer');
  const active = (TABS.find((t) => t.value === tab)?.value ?? 'story_analyzer') as GeneratorKind;
  usePageInfo({ workspace: 'Requirements', tab: TABS.find((t) => t.value === active)?.label });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-[22px] font-semibold">Requirements</h1>
      <Tabs items={[...TABS]} value={tab} onChange={setTab} className="-mb-1" />
      <GeneratorScreen kind={active} />
    </div>
  );
}
