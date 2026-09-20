'use client';

import { COVERAGE_FOCI, DEFAULT_COVERAGE_FOCUS } from '@/lib/generators/test-cases/request';
import { Checkbox } from '@/components/ui/checkbox';
import { FormField } from '@/components/ui/form-field';
import { Input, Textarea } from '@/components/ui/input';
import { fieldArray, fieldValue, type FormProps } from './types';

export function TestCasesForm({ value, errors, onField }: FormProps) {
  const userStory = fieldValue(value, 'user_story');
  const coverage = fieldArray(value, 'coverage_focus');
  const effectiveCoverage = coverage.length > 0 ? coverage : [...DEFAULT_COVERAGE_FOCUS];
  const techStack = fieldValue(value, 'tech_stack');
  const instructions = fieldValue(value, 'instructions');

  const toggleCoverage = (focus: string, checked: boolean) => {
    const next = checked
      ? [...effectiveCoverage, focus]
      : effectiveCoverage.filter((f) => f !== focus);
    onField('coverage_focus', next);
  };

  return (
    <div className="flex flex-col gap-3 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
      <FormField label="User Story / Feature Requirement" error={errors.user_story}>
        <Textarea
          value={userStory}
          onChange={(e) => onField('user_story', e.target.value)}
          placeholder="As a shopper, I want to save items for later so I can buy them on my next visit."
          rows={7}
          aria-invalid={Boolean(errors.user_story)}
        />
      </FormField>
      <FormField
        label="Coverage focus"
        error={errors.coverage_focus}
        helper="At least one area is required."
      >
        <div className="grid grid-cols-2 gap-1.5">
          {COVERAGE_FOCI.map((focus) => (
            <Checkbox
              key={focus}
              label={focus}
              checked={effectiveCoverage.includes(focus)}
              onCheckedChange={(checked) => toggleCoverage(focus, checked)}
            />
          ))}
        </div>
      </FormField>
      <FormField label="Tech Stack (optional)" error={errors.tech_stack}>
        <Input
          value={techStack}
          onChange={(e) => onField('tech_stack', e.target.value)}
          placeholder="Next.js, Node API, Postgres"
        />
      </FormField>
      <FormField label="Additional instructions (optional)" error={errors.instructions}>
        <Textarea
          value={instructions}
          onChange={(e) => onField('instructions', e.target.value)}
          placeholder="e.g. Add accessibility-focused cases for the cart page"
          rows={2}
        />
      </FormField>
    </div>
  );
}
