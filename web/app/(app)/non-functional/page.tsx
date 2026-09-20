'use client';

import { Gauge } from 'lucide-react';
import { EmptyState } from '@/components/ui/empty-state';
import { usePageInfo } from '@/components/shell/shell-context';

export default function NonFunctionalPage() {
  usePageInfo({ workspace: 'Non-functional' });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-[22px] font-semibold">Non-functional</h1>
      <EmptyState
        icon={Gauge}
        headline="Non-functional testing arrives in a later phase"
        description="You'll turn a HAR recording into a k6 performance test and analyze the results here."
      />
    </div>
  );
}
