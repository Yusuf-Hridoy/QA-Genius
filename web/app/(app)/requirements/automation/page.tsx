'use client';

import { useMemo } from 'react';
import { GeneratorScreen } from '@/components/generators/generator-screen';
import { RunStepper } from '@/components/requirements/run-stepper';
import { usePageInfo } from '@/components/shell/shell-context';
import { useRunStore } from '@/lib/store/run';

/** Step 4 — Automation, with the scenario prefilled from the selected cases. */
export default function AutomationStepPage() {
  usePageInfo({ workspace: 'Requirements', tab: 'Automation' });
  const prefill = useRunStore((s) => s.run.automation);

  const initialValues = useMemo<Record<string, unknown> | undefined>(
    () => (prefill ? { scenario: prefill.scenarioPrefill } : undefined),
    [prefill],
  );

  return (
    <div className="flex flex-col gap-4">
      <RunStepper current="automation" />
      {prefill?.truncated ? (
        <p className="text-[12px] text-muted">
          Prefill truncated at 5 000 characters: {prefill.scenarioPrefill.length} of the selected
          cases are included.
        </p>
      ) : null}
      <GeneratorScreen
        key={`automation-${prefill?.updatedAt ?? 'blank'}`}
        kind="automation_script"
        initialValues={initialValues}
      />
    </div>
  );
}
