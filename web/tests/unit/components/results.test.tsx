import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { StoryResult } from '@/components/results/story-result';
import { TestCasesResult } from '@/components/results/test-cases-result';
import { BugReportResult } from '@/components/results/bug-report-result';
import { AutomationResult } from '@/components/results/automation-result';
import { KeyBadge } from '@/components/shell/key-badge';
import { useKeysStore } from '@/lib/store/keys';

const FIXTURES = join(__dirname, '..', '..', '..', 'fixtures');
const storyOutput = JSON.parse(
  readFileSync(join(FIXTURES, 'story_analyzer', 'sample-output.json'), 'utf8'),
) as Record<string, unknown>;
const testCasesOutput = JSON.parse(
  readFileSync(join(FIXTURES, 'test_cases', 'sample-output.json'), 'utf8'),
) as Record<string, unknown>;

describe('StoryResult', () => {
  it('maps INVEST values to pills', () => {
    render(<StoryResult data={storyOutput} isLoading={false} />);
    for (const el of screen.getAllByText('PASS')) {
      expect(el.closest('span')).toHaveClass('bg-ok-bg');
    }
    for (const el of screen.getAllByText('PARTIAL')) {
      expect(el.closest('span')).toHaveClass('bg-warn-bg');
    }
    for (const el of screen.getAllByText('FAIL')) {
      expect(el.closest('span')).toHaveClass('bg-bad-bg');
    }
  });

  it('renders a partial stream without crashing', () => {
    expect(() =>
      render(<StoryResult data={{ ambiguity_score: 40, clarity_label: 'Needs Work' }} isLoading />),
    ).not.toThrow();
    expect(screen.getByTestId('story-result')).toBeInTheDocument();
  });
});

describe('TestCasesResult', () => {
  it('renders every case and filtering reduces the count', async () => {
    const user = userEvent.setup();
    render(<TestCasesResult data={testCasesOutput} isLoading={false} />);
    const all = screen.getAllByTestId('test-case-card');
    expect(all.length).toBe((testCasesOutput.test_cases as unknown[]).length);

    await user.click(screen.getByRole('button', { name: 'Negative' }));
    const filtered = screen.getAllByTestId('test-case-card');
    expect(filtered.length).toBeLessThan(all.length);
    expect(filtered.length).toBe(
      (testCasesOutput.test_cases as { category: string }[]).filter(
        (tc) => tc.category === 'Negative',
      ).length,
    );

    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getAllByTestId('test-case-card').length).toBe(all.length);
  });

  it('shows the result chrome for a mid-stream object', () => {
    render(<TestCasesResult data={{ test_cases: [] }} isLoading />);
    expect(screen.getByTestId('test-cases-result')).toBeInTheDocument();
  });
});

describe('BugReportResult', () => {
  it('renders title, pills, and steps from a partial object', () => {
    render(
      <BugReportResult
        data={{
          title: 'Checkout button unresponsive',
          severity: 'High',
          steps_to_reproduce: ['Open checkout'],
        }}
        isLoading={false}
      />,
    );
    expect(
      screen.getByRole('heading', { name: 'Checkout button unresponsive' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Severity: High')).toBeInTheDocument();
    expect(screen.getByText('Open checkout')).toBeInTheDocument();
  });
});

describe('AutomationResult', () => {
  it('renders the file tree and selects the first file', () => {
    render(
      <AutomationResult
        data={{
          framework: 'Playwright (JavaScript)',
          test_file_name: 'tests/a.spec.ts',
          test_code: "test('a', async () => {});",
        }}
        isLoading={false}
      />,
    );
    expect(screen.getByRole('button', { name: 'tests/a.spec.ts' })).toBeInTheDocument();
  });
});

describe('KeyBadge', () => {
  it('warns without a key and shows the provider with one', () => {
    useKeysStore.setState({ keys: [], defaultKeyId: null });
    const { rerender } = render(<KeyBadge />);
    expect(screen.getByText('No key — add one')).toBeInTheDocument();

    useKeysStore.setState({
      keys: [
        {
          id: 'k1',
          provider: 'gemini',
          label: 'Gemini',
          apiKey: 'abcdef1234567890',
          createdAt: new Date().toISOString(),
        },
      ],
      defaultKeyId: 'k1',
    });
    rerender(<KeyBadge />);
    expect(screen.getByText(/Google Gemini · your key · never stored/)).toBeInTheDocument();
  });
});
