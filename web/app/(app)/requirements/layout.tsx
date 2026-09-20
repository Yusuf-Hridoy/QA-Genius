'use client';

import { useRouter } from 'next/navigation';
import { useRunStore } from '@/lib/store/run';
import { Button } from '@/components/ui/button';

/**
 * Requirements workspace shell: title, New run action, and the step content.
 * The per-step RunStepper is rendered by each step page (it needs the
 * current step); this layout owns the shared header.
 */
export default function RequirementsLayout({ children }: { children: React.ReactNode }) {
  const startNewRun = useRunStore((s) => s.startNewRun);
  const router = useRouter();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-[22px] font-semibold">Requirements</h1>
        <Button
          variant="ghost"
          onClick={() => {
            startNewRun();
            router.push('/requirements/story');
          }}
        >
          New run
        </Button>
      </div>
      {children}
    </div>
  );
}
