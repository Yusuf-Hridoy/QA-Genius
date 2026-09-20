'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Sidebar } from './sidebar';
import { TopBar } from './top-bar';
import { ShellProvider, useShell } from './shell-context';

function Drawer() {
  const { drawerOpen, setDrawerOpen } = useShell();
  const pathname = usePathname();

  if (!drawerOpen) return null;

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div className="absolute inset-0 bg-black/30" onClick={() => setDrawerOpen(false)} />
      <div className="absolute inset-y-0 left-0">
        <Sidebar onNavigate={() => setDrawerOpen(false)} />
      </div>
      {/* close drawer on route change */}
      <span className="hidden">{pathname}</span>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  // Client-only marker so e2e tests can wait for hydration before interacting
  // (React attaches event handlers only after hydration in dev mode).
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return (
    <ShellProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-[var(--qg-radius)] focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-ink"
      >
        Skip to content
      </a>
      <div className="flex h-screen overflow-hidden" data-hydrated={hydrated ? 'true' : undefined}>
        <aside className="hidden shrink-0 lg:block">
          <Sidebar />
        </aside>
        <Drawer />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main id="main" className="flex-1 overflow-y-auto px-5 py-4 sm:px-6" tabIndex={-1}>
            <div className="mx-auto max-w-[1280px]">{children}</div>
          </main>
        </div>
      </div>
    </ShellProvider>
  );
}
