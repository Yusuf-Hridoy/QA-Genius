import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Pill } from '@/components/ui/pill';
import { MetricCard } from '@/components/ui/metric-card';
import { FormField } from '@/components/ui/form-field';
import { Input } from '@/components/ui/input';
import { EmptyState } from '@/components/ui/empty-state';
import { FileText } from 'lucide-react';

describe('Pill', () => {
  it('renders semantic tone classes', () => {
    const { container, rerender } = render(<Pill tone="ok">fine</Pill>);
    expect(container.firstChild).toHaveClass('bg-ok-bg', 'text-ok-fg');
    rerender(<Pill tone="bad">broken</Pill>);
    expect(container.firstChild).toHaveClass('bg-bad-bg', 'text-bad-fg');
    rerender(<Pill>plain</Pill>);
    expect(container.firstChild).toHaveClass('bg-card-2');
  });
});

describe('MetricCard', () => {
  it('renders label, value, and sub', () => {
    render(<MetricCard label="Total" value={12} sub="test cases" />);
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('test cases')).toBeInTheDocument();
  });
});

describe('FormField', () => {
  it('shows the error instead of the helper when both are set', () => {
    render(
      <FormField label="Story" helper="helper text" error="must be longer">
        <Input />
      </FormField>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('must be longer');
    expect(screen.queryByText('helper text')).not.toBeInTheDocument();
  });

  it('colours the counter by length', () => {
    const { rerender } = render(
      <FormField label="Story" maxChars={100} charCount={50}>
        <Input />
      </FormField>,
    );
    expect(screen.getByText('50 / 100')).toHaveClass('text-muted');
    rerender(
      <FormField label="Story" maxChars={100} charCount={95}>
        <Input />
      </FormField>,
    );
    expect(screen.getByText('95 / 100')).toHaveClass('text-warn-fg');
    rerender(
      <FormField label="Story" maxChars={100} charCount={120}>
        <Input />
      </FormField>,
    );
    expect(screen.getByText('120 / 100')).toHaveClass('text-bad-fg');
  });
});

describe('EmptyState', () => {
  it('renders headline, one sentence, and an action', () => {
    const onClick = () => {};
    render(
      <EmptyState
        icon={FileText}
        headline="Analyze a story"
        description="Paste a user story to score its clarity."
        action={{ label: 'Load example', onClick }}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Analyze a story' })).toBeInTheDocument();
    expect(screen.getByText('Paste a user story to score its clarity.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load example' })).toBeInTheDocument();
  });
});
