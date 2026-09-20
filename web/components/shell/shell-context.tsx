'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type PageInfo = { workspace: string; tab?: string };

const ShellContext = createContext<{
  pageInfo: PageInfo;
  setPageInfo: (info: PageInfo) => void;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
}>({
  pageInfo: { workspace: '' },
  setPageInfo: () => {},
  drawerOpen: false,
  setDrawerOpen: () => {},
});

export function ShellProvider({ children }: { children: ReactNode }) {
  const [pageInfo, setPageInfo] = useState<PageInfo>({ workspace: '' });
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <ShellContext.Provider value={{ pageInfo, setPageInfo, drawerOpen, setDrawerOpen }}>
      {children}
    </ShellContext.Provider>
  );
}

export function useShell() {
  return useContext(ShellContext);
}

/** Pages call this to set the top-bar breadcrumb. */
export function usePageInfo(info: PageInfo) {
  const { setPageInfo } = useShell();
  const workspace = info.workspace;
  const tab = info.tab;
  useEffect(() => {
    setPageInfo({ workspace, tab });
  }, [workspace, tab, setPageInfo]);
}
