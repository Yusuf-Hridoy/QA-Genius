'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useRunStore } from '@/lib/store/run';
import { useKeysStore } from '@/lib/store/keys';
import { useDefaultKey } from '@/components/shell/key-badge';
import { buildByokHeaders } from '@/lib/llm/byok';
import { showNoKeyToast } from '@/lib/client/api-error';
import { generateOne } from '@/lib/client/generate-one';
import { TestCaseList } from '@/lib/generators/test-cases/schema';
import { diffTestCases, type TestCasesDiff } from '@/lib/diff/test-cases';
import { TestCasesDiffView } from '@/components/diff/test-cases-diff-view';
import { Button } from '@/components/ui/button';

export const TEST_CASES_REFINE_PLACEHOLDER =
  'Make the negative cases stricter and add one boundary case for the tenant lockout window';

/**
 * Refine loop for test cases: same request with instructions plus the
 * compact previous block, deterministic diff, accept/keep/undo.
 */
export function TestCasesRefinePanel({
  onAccepted,
  preset,
}: {
  onAccepted: () => void;
  /** Coverage recovery: prefill instructions and open the panel. */
  preset?: { text: string; nonce: number } | null;
}) {
  const defaultKey = useDefaultKey();
  const tier = useKeysStore((s) => s.tier);
  const testCases = useRunStore((s) => s.run.testCases);
  const acceptTestCasesRevision = useRunStore((s) => s.acceptTestCasesRevision);
  const undoTestCases = useRunStore((s) => s.undoTestCases);

  const [open, setOpen] = useState(false);
  const [instructions, setInstructions] = useState('');
  const [running, setRunning] = useState(false);
  const [diff, setDiff] = useState<TestCasesDiff | null>(null);
  const [pending, setPending] = useState<{ output: TestCaseList; requestId?: string } | null>(null);

  useEffect(() => {
    if (preset) {
      setInstructions(preset.text.slice(0, 1000));
      setOpen(true);
    }
  }, [preset]);

  if (!testCases?.output) return null;

  const generateRevision = async () => {
    if (!defaultKey) {
      showNoKeyToast();
      return;
    }
    const current = useRunStore.getState().run.testCases;
    if (!current?.output) return;
    setRunning(true);
    try {
      const previous = current.output.test_cases
        .slice(0, 60)
        .map((c) => ({ id: c.id, title: c.title }));
      const criteria = useRunStore.getState().run.criteria?.items ?? [];
      const body = {
        ...current.input,
        criteria:
          criteria.length > 0 ? criteria.map((c) => ({ id: c.id, text: c.text })) : undefined,
        previous,
        instructions: instructions.trim(),
      };
      const { data, meta } = await generateOne(
        'test_cases',
        body,
        buildByokHeaders(defaultKey, tier),
      );
      const parsed = TestCaseList.safeParse(data);
      if (!parsed.success) {
        toast.error('The revision returned output that could not be read. Try again.');
        return;
      }
      setPending({
        output: parsed.data,
        requestId: meta.requestId,
      });
      setDiff(diffTestCases(current.output.test_cases, parsed.data.test_cases));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'The revision failed. Try again.');
    } finally {
      setRunning(false);
    }
  };

  if (diff && pending) {
    return (
      <TestCasesDiffView
        diff={diff}
        canUndo={(testCases.history?.length ?? 0) > 0}
        onAccept={() => {
          acceptTestCasesRevision(pending.output, { requestId: pending.requestId });
          setDiff(null);
          setPending(null);
          setOpen(false);
          setInstructions('');
          onAccepted();
        }}
        onKeep={() => {
          setDiff(null);
          setPending(null);
          setOpen(false);
          setInstructions('');
        }}
        onUndo={() => {
          undoTestCases();
          setDiff(null);
          setPending(null);
          setOpen(false);
          setInstructions('');
          onAccepted();
        }}
      />
    );
  }

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Refine
      </Button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-border bg-card p-3">
      <label htmlFor="test-cases-refine" className="text-[13px] font-medium">
        Refine test cases
      </label>
      <textarea
        id="test-cases-refine"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value.slice(0, 1000))}
        rows={3}
        maxLength={1000}
        placeholder={TEST_CASES_REFINE_PLACEHOLDER}
        className="w-full rounded-[var(--radius)] border border-border bg-card px-2.5 py-2 text-[13px] text-text focus-visible:outline-none"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          onClick={generateRevision}
          loading={running}
          disabled={instructions.trim().length === 0}
        >
          Generate revision
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <span className="text-[12px] text-muted">{instructions.length}/1000</span>
      </div>
    </div>
  );
}
