'use client';

import { STORY_TYPES } from '@/lib/generators/story-analyzer/request';
import { FormField } from '@/components/ui/form-field';
import { Input, Textarea } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { fieldValue, type FormProps } from './types';

export function StoryAnalyzerForm({ value, errors, onField }: FormProps) {
  const userStory = fieldValue(value, 'user_story');
  const context = fieldValue(value, 'project_context');
  const instructions = fieldValue(value, 'instructions');

  return (
    <div className="flex flex-col gap-3 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
      <FormField label="User Story / Requirement" error={errors.user_story}>
        <Textarea
          value={userStory}
          onChange={(e) => onField('user_story', e.target.value)}
          placeholder="As a shopper, I want to save items for later so I can buy them on my next visit."
          rows={6}
          aria-invalid={Boolean(errors.user_story)}
        />
      </FormField>
      <FormField label="Story type" helper={errors.story_type} className="text-[13px]">
        <Select
          value={fieldValue(value, 'story_type', 'User Story')}
          onChange={(e) => onField('story_type', e.target.value)}
        >
          {STORY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Project Context (optional)" error={errors.project_context}>
        <Input
          value={context}
          onChange={(e) => onField('project_context', e.target.value)}
          placeholder="E-commerce storefront with guest checkout and admin console"
        />
      </FormField>
      <FormField label="Additional instructions (optional)" error={errors.instructions}>
        <Textarea
          value={instructions}
          onChange={(e) => onField('instructions', e.target.value)}
          placeholder="e.g. Focus on security-related ambiguities"
          rows={2}
        />
      </FormField>
    </div>
  );
}
