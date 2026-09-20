'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { activeStep } from '@/lib/pipeline/steps';
import { useRunStore } from '@/lib/store/run';

/** /requirements redirects to the active pipeline step. */
export default function RequirementsRedirect() {
  const run = useRunStore((s) => s.run);
  const router = useRouter();

  useEffect(() => {
    const step = activeStep(run);
    router.replace(`/requirements/${step === 'test-cases' ? 'test-cases' : step}`);
  }, [run, router]);

  return null;
}
