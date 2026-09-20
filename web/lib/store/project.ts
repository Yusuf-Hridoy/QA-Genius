'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Project = {
  name: string;
  stack: string;
};

export type ProjectState = {
  project: Project;
  setProject: (p: Project) => void;
};

/** Seeded once on first run with the Aurora Storefront demo project. */
export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      project: { name: 'Aurora Storefront', stack: 'Next.js · Playwright TS · POM' },
      setProject: (project) => {
        set({ project });
      },
    }),
    { name: 'qag.project.v1', version: 1 },
  ),
);
