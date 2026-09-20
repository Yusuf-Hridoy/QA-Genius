import { describe, expect, it } from 'vitest';
import { activeStep, canVisit, stepStatus } from '@/lib/pipeline/steps';
import { newRun } from '@/lib/store/run';

describe('activeStep', () => {
  it('walks story, criteria, test-cases, automation in order', () => {
    const run = newRun('Aurora Storefront');
    expect(activeStep(run)).toBe('story');
    const withStory = {
      ...run,
      story: { input: { user_story: 'x'.repeat(40), story_type: 'User Story' as const } },
    };
    expect(activeStep(withStory)).toBe('story');
    const withOutput = { ...withStory, story: { ...withStory.story, output: undefined } };
    expect(activeStep(withOutput)).toBe('story');
  });

  it('advances past completed steps', () => {
    const run = newRun('Aurora Storefront');
    run.story = {
      input: { user_story: 'x'.repeat(40), story_type: 'User Story' },
      output: undefined,
    };
    expect(activeStep(run)).toBe('story');
    run.criteria = { items: [{ id: 'AC-1', text: 'Something' }], source: 'manual' };
    expect(activeStep(run)).toBe('story');
  });
});

describe('canVisit', () => {
  it('gates test-cases on criteria or a story', () => {
    expect(canVisit(newRun(), 'test-cases')).toBe(false);
    const withStory = newRun();
    withStory.story = { input: { user_story: 'x'.repeat(40), story_type: 'User Story' } };
    expect(canVisit(withStory, 'test-cases')).toBe(true);
  });

  it('gates automation on started test cases', () => {
    expect(canVisit(newRun(), 'automation')).toBe(false);
  });
});

describe('stepStatus', () => {
  it('marks current, done, and todo', () => {
    const run = newRun();
    expect(stepStatus(run, 'story', 'story')).toBe('active');
    expect(stepStatus(run, 'story', 'criteria')).toBe('todo');
    run.criteria = { items: [{ id: 'AC-1', text: 'Something' }], source: 'manual' };
    expect(stepStatus(run, 'criteria', 'criteria')).toBe('active');
  });
});
