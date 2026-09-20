'use client';

import { DEVICE_TYPES, computeReproducibility } from '@/lib/generators/bug-report/derived';
import { FormField } from '@/components/ui/form-field';
import { Input, Textarea } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Pill } from '@/components/ui/pill';
import { fieldInt, fieldValue, type FormProps } from './types';

export function BugReportForm({ value, errors, onField }: FormProps) {
  const rawBug = fieldValue(value, 'raw_bug');
  const deviceType = fieldValue(value, 'device_type', 'Not specified');
  const totalAttempts = fieldInt(value, 'total_attempts', 1);
  const successfulAttempts = fieldInt(value, 'successful_attempts', 0);
  const instructions = fieldValue(value, 'instructions');

  const computedRepro = computeReproducibility(totalAttempts, successfulAttempts);
  const allSuccessful = successfulAttempts === totalAttempts && totalAttempts > 0;

  const numberField = (label: string, field: string, current: number, error?: string) => (
    <FormField label={label} error={error}>
      <Input
        type="number"
        min={field === 'total_attempts' ? 1 : 0}
        value={Number.isFinite(current) ? current : ''}
        onChange={(e) => onField(field, e.target.value === '' ? undefined : Number(e.target.value))}
      />
    </FormField>
  );

  return (
    <div className="flex flex-col gap-3 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
      <FormField label="Raw Bug Notes" error={errors.raw_bug}>
        <Textarea
          value={rawBug}
          onChange={(e) => onField('raw_bug', e.target.value)}
          placeholder="Checkout button does nothing on the second click in Safari, 3 of 5 attempts, cart total shows 0"
          rows={6}
          aria-invalid={Boolean(errors.raw_bug)}
        />
      </FormField>

      <FormField label="Device type">
        <Select value={deviceType} onChange={(e) => onField('device_type', e.target.value)}>
          {DEVICE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
      </FormField>

      <div className="grid grid-cols-2 gap-3">
        <FormField label="OS version (optional)" error={errors.os_version}>
          <Input
            value={fieldValue(value, 'os_version')}
            onChange={(e) => onField('os_version', e.target.value)}
            placeholder="Windows 11, iOS 17.2"
          />
        </FormField>
        <FormField label="Browser / app version (optional)" error={errors.browser_version}>
          <Input
            value={fieldValue(value, 'browser_version')}
            onChange={(e) => onField('browser_version', e.target.value)}
            placeholder="Chrome 131, app v2.4.0"
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <FormField label="Build / environment (optional)" error={errors.build_env}>
          <Input
            value={fieldValue(value, 'build_env')}
            onChange={(e) => onField('build_env', e.target.value)}
            placeholder="Staging, release 2026.09"
          />
        </FormField>
        <FormField label="URL (optional)" error={errors.bug_url}>
          <Input
            value={fieldValue(value, 'bug_url')}
            onChange={(e) => onField('bug_url', e.target.value)}
            placeholder="https://staging.aurora-shop.dev/checkout"
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {numberField('Total attempts', 'total_attempts', totalAttempts, errors.total_attempts)}
        {numberField(
          'Times reproduced',
          'successful_attempts',
          successfulAttempts,
          errors.successful_attempts,
        )}
      </div>
      <div className="flex flex-col gap-1">
        {computedRepro ? <Pill tone="info">{computedRepro}</Pill> : null}
        {allSuccessful ? (
          <p className="text-[12px] text-warn-fg">
            Successful attempts equals total attempts — this may not be a reproducible bug.
          </p>
        ) : null}
      </div>

      <FormField label="Additional instructions (optional)" error={errors.instructions}>
        <Textarea
          value={instructions}
          onChange={(e) => onField('instructions', e.target.value)}
          placeholder="e.g. Flag any PII in the notes before formatting"
          rows={2}
        />
      </FormField>
    </div>
  );
}
