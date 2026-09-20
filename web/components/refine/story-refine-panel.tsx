'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useRunStore } from '@/lib/store/run';
import { useKeysStore } from '@/lib/store/keys';
import { useDefaultKey } from '@/components/shell/key-badge';
import { buildByokHeaders } from '@/lib/llm/byok';
import { showNoKeyToast } from '@/lib/client/api-error';
import { generateOne } from '@/lib/client/generate-one';
import { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import { diffStory, type StoryDiff } from '@/lib/diff/story';
import { StoryDiffView } from '@/components/diff/story-diff-view';
import { Button } from '@/components/ui/button';

/** Refine loop for the story analyzer: same request with instructions, field diff, accept/keep. */
export function StoryRefinePanel({ onAccepted }: { onAccepted: () => void }) {
  const defaultKey = useDefaultKey();
  const tier = useKeysStore((s) => s.tier);
  const story = useRunStore((s) => s.run.story);
  const setStory = useRunStore((s) => s.setStory);

  const [open, setOpen] = useState(false);
  const [instructions, setInstructions] = useState('');
  const [running, setRunning] = useState(false);
  const [diff, setDiff] = useState<StoryDiff | null>(null);
  const [pending, setPending] = useState<AmbiguityAnalysis | null>(null);

  if (!story?.output) return null;

  const generateRevision = async () => {
    if (!defaultKey) {
      showNoKeyToast();
      return;
    }
    const current = useRunStore.getState().run.story;
    if (!current?.output) return;
    setRunning(true);
    try {
      const body = { ...current.input, instructions: instructions.trim() };
      const { data } = await generateOne(
        'story_analyzer',
        body,
        buildByokHeaders(defaultKey, tier),
      );
      const parsed = AmbiguityAnalysis.safeParse(data);
      if (!parsed.success) {
        toast.error('The revision returned output that could not be read. Try again.');
        return;
      }
      setPending(parsed.data);
      setDiff(diffStory(current.output, parsed.data));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'The revision failed. Try again.');
    } finally {
      setRunning(false);
    }
  };

  if (diff && pending) {
    return (
      <StoryDiffView
        diff={diff}
        onAccept={() => {
          const current = useRunStore.getState().run.story;
          if (current) setStory(current.input, pending);
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
      <label htmlFor="story-refine" className="text-[13px] font-medium">
        Refine story analysis
      </label>
      <textarea
        id="story-refine"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value.slice(0, 1000))}
        rows={3}
        maxLength={1000}
        placeholder="Focus on the error paths and add a scenario for expired sessions"
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
