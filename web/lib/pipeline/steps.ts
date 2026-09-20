import type { Run } from './types';

export type StepId = 'story' | 'criteria' | 'test-cases' | 'automation';

export const STEPS: Array<{ id: StepId; label: string; href: string }> = [
  { id: 'story', label: 'Story', href: '/requirements/story' },
  { id: 'criteria', label: 'Acceptance criteria', href: '/requirements/criteria' },
  { id: 'test-cases', label: 'Test cases', href: '/requirements/test-cases' },
  { id: 'automation', label: 'Automation', href: '/requirements/automation' },
];

/** First incomplete step; the /requirements redirect target. */
export function activeStep(run: Run): StepId {
  if (!run.story?.output) return 'story';
  if (!run.criteria || run.criteria.items.length === 0) return 'criteria';
  if (!run.testCases?.output) return 'test-cases';
  return 'automation';
}

export type StepStatus = 'done' | 'active' | 'todo';

/** Step 3 needs criteria or a story; step 4 needs test cases started. */
export function canVisit(run: Run, step: StepId): boolean {
  switch (step) {
    case 'story':
      return true;
    case 'criteria':
      return true;
    case 'test-cases':
      return (run.criteria?.items.length ?? 0) > 0 || run.story?.input !== undefined;
    case 'automation':
      return run.testCases !== undefined;
  }
}

export function stepStatus(run: Run, current: StepId, step: StepId): StepStatus {
  if (step === current) return 'active';
  const done =
    (step === 'story' && run.story?.output !== undefined) ||
    (step === 'criteria' && (run.criteria?.items.length ?? 0) > 0) ||
    (step === 'test-cases' && run.testCases?.output !== undefined);
  return done ? 'done' : 'todo';
}
