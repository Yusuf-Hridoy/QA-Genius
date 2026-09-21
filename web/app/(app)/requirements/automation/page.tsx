'use client';

import { useCallback, useMemo, useState } from 'react';
import { GeneratorScreen } from '@/components/generators/generator-screen';
import { RunStepper } from '@/components/requirements/run-stepper';
import { AutomationCheckFlow } from '@/components/results/automation-check-flow';
import { usePageInfo } from '@/components/shell/shell-context';
import { useRunStore } from '@/lib/store/run';
import { AutomationRequest } from '@/lib/generators/automation-script/request';
import type { AutomationScript } from '@/lib/generators/automation-script/schema';
import { hashJson } from '@/lib/automation/syntax-store';

/** Step 4 — Automation, with the scenario prefilled from the selected cases. */
export default function AutomationStepPage() {
  usePageInfo({ workspace: 'Requirements', tab: 'Automation' });
  const prefill = useRunStore((s) => s.run.automation);
  const [lastInput, setLastInput] = useState<
    { key: string; input: Record<string, unknown> } | undefined
  >(undefined);
  const [repairNonce, setRepairNonce] = useState(0);

  const initialValues = useMemo<Record<string, unknown> | undefined>(
    () => (prefill ? { scenario: prefill.scenarioPrefill } : undefined),
    [prefill],
  );

  // Keep the last valid request keyed by its output: the syntax repair loop
  // resubmits it with fix-only instructions plus the previously generated
  // files. Keying avoids a stale request when the flow renders first.
  const onResult = useCallback(
    (output: Record<string, unknown>, input: Record<string, unknown>) => {
      if (AutomationRequest.safeParse(input).success)
        setLastInput({ key: hashJson(output), input });
    },
    [],
  );

  /** Adopt the repaired project so the result, diagnostics and exports follow it. */
  const onRepaired = useCallback((script: AutomationScript) => {
    try {
      window.sessionStorage.setItem('qag.result.automation_script', JSON.stringify(script));
    } catch {
      // storage unavailable — the remount still refreshes the view
    }
    setRepairNonce((n) => n + 1);
  }, []);

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
        key={`automation-${prefill?.updatedAt ?? 'blank'}-${repairNonce}`}
        kind="automation_script"
        initialValues={initialValues}
        onResult={onResult}
        renderResult={({ data, isLoading }) => (
          <AutomationCheckFlow
            data={data}
            isLoading={isLoading}
            inputEntry={lastInput}
            onRepaired={onRepaired}
          />
        )}
      />
    </div>
  );
}
