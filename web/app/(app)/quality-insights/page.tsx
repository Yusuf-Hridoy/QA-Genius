'use client';

import { BarChart3 } from 'lucide-react';
import { EmptyState } from '@/components/ui/empty-state';
import { usePageInfo } from '@/components/shell/shell-context';

export default function QualityInsightsPage() {
  usePageInfo({ workspace: 'Quality insights' });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-[22px] font-semibold">Quality insights</h1>
      <EmptyState
        icon={BarChart3}
        headline="Quality insights arrives in a later phase"
        description="You'll upload Playwright, JUnit, or trace files and get computed metrics with a written summary."
      />
    </div>
  );
}
