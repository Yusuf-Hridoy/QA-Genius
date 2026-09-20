'use client';

import {
  BROWSERS,
  FRAMEWORKS,
  LANGUAGES,
  SITE_TYPES,
  STRUCTURES,
  isPythonFramework,
} from '@/lib/generators/automation-script/request';
import { Checkbox } from '@/components/ui/checkbox';
import { FormField } from '@/components/ui/form-field';
import { Textarea } from '@/components/ui/input';
import { RadioGroup } from '@/components/ui/radio-group';
import { Select } from '@/components/ui/select';
import { fieldArray, fieldValue, type FormProps } from './types';

export function AutomationForm({ value, errors, onField }: FormProps) {
  const scenario = fieldValue(value, 'scenario');
  const framework = fieldValue(value, 'framework', 'Playwright (JavaScript)');
  const language = fieldValue(value, 'language', 'TypeScript');
  const structure = fieldValue(value, 'structure', 'Page Object Model');
  const browsers = fieldArray(value, 'browsers');
  const effectiveBrowsers = browsers.length > 0 ? browsers : ['Chromium'];
  const siteType = fieldValue(value, 'site_type', 'Custom (paste URL above)');
  const instructions = fieldValue(value, 'instructions');

  const toggleBrowser = (browser: string, checked: boolean) => {
    const next = checked
      ? [...effectiveBrowsers, browser]
      : effectiveBrowsers.filter((b) => b !== browser);
    onField('browsers', next);
  };

  return (
    <div className="flex flex-col gap-3 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
      <FormField
        label="Test Scenario Description"
        error={errors.scenario}
        helper="Include the target URL for custom sites."
      >
        <Textarea
          value={scenario}
          onChange={(e) => onField('scenario', e.target.value)}
          placeholder="On https://staging.aurora-shop.dev/login, verify the account locks after 5 failed attempts and shows the reset-password prompt."
          rows={7}
          aria-invalid={Boolean(errors.scenario)}
        />
      </FormField>

      <RadioGroup
        label="Framework"
        options={FRAMEWORKS.map((f) => ({ value: f, label: f }))}
        value={framework}
        onChange={(v) => onField('framework', v)}
      />

      {/* v1 behaviour: Python frameworks generate Python code, so the language
          radio is hidden and the prompt builder forces 'Python'. */}
      {isPythonFramework(framework as (typeof FRAMEWORKS)[number]) ? null : (
        <RadioGroup
          label="Language"
          options={LANGUAGES.map((l) => ({ value: l, label: l }))}
          value={language}
          onChange={(v) => onField('language', v)}
        />
      )}

      <RadioGroup
        label="Structure"
        options={STRUCTURES.map((s) => ({ value: s, label: s }))}
        value={structure}
        onChange={(v) => onField('structure', v)}
      />

      <FormField label="Browsers" error={errors.browsers}>
        <div className="flex gap-4">
          {BROWSERS.map((browser) => (
            <Checkbox
              key={browser}
              label={browser}
              checked={effectiveBrowsers.includes(browser)}
              onCheckedChange={(checked) => toggleBrowser(browser, checked)}
            />
          ))}
        </div>
      </FormField>

      <FormField label="Target site">
        <Select value={siteType} onChange={(e) => onField('site_type', e.target.value)}>
          {SITE_TYPES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </FormField>

      <FormField label="Additional instructions (optional)" error={errors.instructions}>
        <Textarea
          value={instructions}
          onChange={(e) => onField('instructions', e.target.value)}
          placeholder="e.g. Use data-testid locators and add a smoke tag"
          rows={2}
        />
      </FormField>
    </div>
  );
}
