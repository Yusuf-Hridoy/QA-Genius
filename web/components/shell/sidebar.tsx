'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart3, Bug, Check, Gauge, ListChecks, Settings } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { ProjectCard } from './project-card';
import { KeyBadge } from './key-badge';

export const NAV_ITEMS = [
  { href: '/requirements', label: 'Requirements', icon: ListChecks },
  { href: '/bug-desk', label: 'Bug desk', icon: Bug },
  { href: '/quality-insights', label: 'Quality insights', icon: BarChart3 },
  { href: '/non-functional', label: 'Non-functional', icon: Gauge },
] as const;

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-58 flex-col gap-1 border-r border-border bg-side p-3">
      <Link
        href="/requirements"
        onClick={onNavigate}
        className="mb-3 flex items-center gap-2 px-1 py-1"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius)] bg-accent">
          <Check className="h-4 w-4 text-accent-ink" aria-hidden />
        </span>
        <span className="font-display text-[17px] font-semibold">QA-Genius</span>
      </Link>

      <nav aria-label="Workspaces" className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex items-center gap-2.5 rounded-[var(--radius)] px-2.5 py-2 text-[13px] font-medium transition-colors duration-[var(--dur)]',
                active ? 'bg-card text-accent' : 'text-text-2 hover:bg-card-2',
              )}
            >
              <item.icon className="h-[18px] w-[18px]" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex-1" />

      <div className="mb-2">
        <ProjectCard />
      </div>
      <div className="mb-2">
        <KeyBadge />
      </div>

      <Link
        href="/settings/keys"
        onClick={onNavigate}
        className="flex items-center gap-2.5 rounded-[var(--radius)] px-2.5 py-2 text-[13px] font-medium text-text-2 transition-colors duration-[var(--dur)] hover:bg-card-2"
      >
        <Settings className="h-[18px] w-[18px]" aria-hidden />
        Settings
      </Link>
    </div>
  );
}
