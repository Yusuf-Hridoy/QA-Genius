'use client';

import { Pill, type PillTone } from '@/components/ui/pill';
import type { SyntaxBadge } from '@/lib/automation/syntax-store';

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * Syntax status pill for the Automation result header. Honest naming: this
 * is a parser-based syntax check, never a full type check.
 */
export function AutomationStatusPill({ badge }: { badge: SyntaxBadge }) {
  switch (badge.status) {
    case 'checking':
      return (
        <Pill tone="neutral">
          <span className="animate-pulse">checking…</span>
        </Pill>
      );
    case 'repairing':
      return (
        <Pill tone="neutral">
          <span className="animate-pulse">repairing…</span>
        </Pill>
      );
    case 'clean': {
      const tone: PillTone = 'ok';
      return (
        <Pill tone={tone}>
          syntax clean
          {badge.warnings > 0 ? ` · ${plural(badge.warnings, 'warning', 'warnings')}` : ''}
        </Pill>
      );
    }
    case 'repaired':
      return <Pill tone="warn">repaired · was {plural(badge.wasErrors, 'error', 'errors')}</Pill>;
    case 'errors':
      return (
        <Pill tone="bad">
          {plural(badge.errors, 'error', 'errors')} remain
          {badge.warnings > 0 ? ` · ${plural(badge.warnings, 'warning', 'warnings')}` : ''}
        </Pill>
      );
    case 'unchecked':
      return <Pill tone="neutral">{badge.python ? 'not checked · Python' : 'not checked'}</Pill>;
  }
}
