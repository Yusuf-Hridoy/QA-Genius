'use client';

import { create } from 'zustand';
import { newId } from '@/lib/utils/id';
import type { AmbiguityAnalysis } from '@/lib/generators/story-analyzer/schema';
import type { StoryAnalyzerRequest } from '@/lib/generators/story-analyzer/request';
import type { TestCaseList } from '@/lib/generators/test-cases/schema';
import type { TestCasesRequest } from '@/lib/generators/test-cases/request';
import type { DuelResult } from '@/lib/duel/types';
import type { GenerateMeta, Run } from '@/lib/pipeline/types';
import { withCriterionIds } from '@/lib/pipeline/types';

export const CURRENT_KEY = 'qag.run.current';
export const RECENTS_KEY = 'qag.runs.v1';
export const MAX_RECENTS = 10;
/** localStorage budget for the recent-runs list (metadata + payload). */
export const MAX_RECENTS_BYTES = 1_000_000;

function nowIso(): string {
  return new Date().toISOString();
}

export function newRun(projectName = 'Aurora Storefront'): Run {
  const now = nowIso();
  return { id: newId(), createdAt: now, updatedAt: now, projectName };
}

function touch(run: Run): Run {
  return { ...run, updatedAt: nowIso() };
}

function byteLength(value: string): number {
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(value).length;
  return value.length;
}

/**
 * Cap the recent-runs list: newest first, at most MAX_RECENTS entries and
 * MAX_RECENTS_BYTES total. Oldest evicted first. Pure — unit-tested.
 */
export function evictRecents(runs: Run[]): Run[] {
  const capped = runs.slice(0, MAX_RECENTS);
  let total = byteLength(JSON.stringify(capped));
  let result = capped;
  while (result.length > 0 && total > MAX_RECENTS_BYTES) {
    result = result.slice(0, -1);
    total = byteLength(JSON.stringify(result));
  }
  return result;
}

/** Read the current run back from sessionStorage (exported for tests). */
export function loadCurrent(): Run | null {
  try {
    if (typeof window === 'undefined') return null;
    const raw = window.sessionStorage.getItem(CURRENT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Run;
    if (!parsed || typeof parsed.id !== 'string') return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCurrent(run: Run): void {
  try {
    if (typeof window === 'undefined') return;
    window.sessionStorage.setItem(CURRENT_KEY, JSON.stringify(run));
  } catch {
    // storage full or unavailable — the in-memory run still works
  }
}

export function loadRecents(): Run[] {
  try {
    if (typeof window === 'undefined') return [];
    const raw = window.localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Run[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((r) => r && typeof r.id === 'string');
  } catch {
    return [];
  }
}

function saveRecents(runs: Run[]): void {
  try {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(evictRecents(runs)));
  } catch {
    // quota exceeded — keep the in-memory list
  }
}

export type RunState = {
  run: Run;
  recents: Run[];
  /** New run, keeping the project name unless overridden. */
  startNewRun: (projectName?: string) => void;
  setProjectName: (name: string) => void;
  setStory: (input: StoryAnalyzerRequest, output?: AmbiguityAnalysis, meta?: GenerateMeta) => void;
  setDuel: (duel: DuelResult | undefined) => void;
  /** Replace the whole criteria list; ids are recomputed AC-1..n from order. */
  setCriteria: (texts: string[], source: 'story' | 'manual') => void;
  addCriterion: (text?: string) => void;
  updateCriterion: (index: number, text: string) => void;
  removeCriterion: (index: number) => void;
  reorderCriteria: (from: number, to: number) => void;
  setTestCases: (input: TestCasesRequest, output?: TestCaseList, meta?: GenerateMeta) => void;
  /** Accept a refined revision: current output goes to history. */
  acceptTestCasesRevision: (output: TestCaseList, meta?: GenerateMeta) => void;
  undoTestCases: () => void;
  setSelectedIds: (ids: string[]) => void;
  setSuiteSummary: (summary: { fileName: string; importedAt: string; count: number }) => void;
  setAutomationPrefill: (scenarioPrefill: string, truncated: boolean) => void;
  /** Manual story text for runs that started from scratch (step 2 without step 1). */
  setManualStory: (text: string) => void;
  /** Copy a shared run into this workspace with a fresh id. */
  adoptSharedRun: (shared: Run) => void;
};

/** Re-point the recents list at the latest run (newest first). */
function upsertRecent(recents: Run[], run: Run): Run[] {
  return evictRecents([run, ...recents.filter((r) => r.id !== run.id)]);
}

function persist(run: Run, recents: Run[]): Run[] {
  saveCurrent(run);
  const next = upsertRecent(recents, run);
  saveRecents(next);
  return next;
}

export const useRunStore = create<RunState>()((set, get) => ({
  run: loadCurrent() ?? newRun(),
  recents: loadRecents(),

  startNewRun: (projectName) => {
    const name = projectName ?? get().run.projectName;
    const run = newRun(name);
    saveCurrent(run);
    set({ run });
  },

  setProjectName: (name) => {
    const run = touch({ ...get().run, projectName: name });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setStory: (input, output, meta) => {
    const prev = get().run.story;
    const run = touch({
      ...get().run,
      story: {
        input,
        output: output ?? prev?.output,
        meta: meta ?? prev?.meta,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setDuel: (duel) => {
    const run = touch({ ...get().run, duel });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setCriteria: (texts, source) => {
    const current = get().run.criteria;
    const run = touch({
      ...get().run,
      criteria: {
        items: withCriterionIds(texts),
        source,
        manualStory: source === 'manual' ? current?.manualStory : undefined,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  addCriterion: (text = '') => {
    const current = get().run.criteria;
    const texts = [...(current?.items.map((c) => c.text) ?? []), text];
    const run = touch({
      ...get().run,
      criteria: {
        items: withCriterionIds(texts),
        source: current?.source ?? 'manual',
        manualStory: current?.manualStory,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  updateCriterion: (index, text) => {
    const current = get().run.criteria;
    if (!current || index < 0 || index >= current.items.length) return;
    const texts = current.items.map((c, i) => (i === index ? text : c.text));
    const run = touch({
      ...get().run,
      criteria: {
        items: withCriterionIds(texts),
        source: current.source,
        manualStory: current.manualStory,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  removeCriterion: (index) => {
    const current = get().run.criteria;
    if (!current || index < 0 || index >= current.items.length) return;
    const texts = current.items.filter((_, i) => i !== index).map((c) => c.text);
    const run = touch({
      ...get().run,
      criteria: {
        items: withCriterionIds(texts),
        source: current.source,
        manualStory: current.manualStory,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  reorderCriteria: (from, to) => {
    const current = get().run.criteria;
    if (
      !current ||
      from < 0 ||
      from >= current.items.length ||
      to < 0 ||
      to >= current.items.length
    )
      return;
    if (from === to) return;
    const texts = current.items.map((c) => c.text);
    const [moved] = texts.splice(from, 1);
    texts.splice(to, 0, moved as string);
    const run = touch({
      ...get().run,
      criteria: {
        items: withCriterionIds(texts),
        source: current.source,
        manualStory: current.manualStory,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setTestCases: (input, output, meta) => {
    const prev = get().run.testCases;
    const run = touch({
      ...get().run,
      testCases: {
        input,
        output: output ?? prev?.output,
        meta: meta ?? prev?.meta,
        history: prev?.history ?? [],
        selectedIds: prev?.selectedIds,
      },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  acceptTestCasesRevision: (output, meta) => {
    const prev = get().run.testCases;
    if (!prev) return;
    const history = prev.output ? [...prev.history, prev.output] : prev.history;
    const run = touch({
      ...get().run,
      testCases: { ...prev, output, meta: meta ?? prev.meta, history },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  undoTestCases: () => {
    const prev = get().run.testCases;
    if (!prev || prev.history.length === 0) return;
    const history = [...prev.history];
    const output = history.pop() as TestCaseList;
    const run = touch({ ...get().run, testCases: { ...prev, output, history } });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setSelectedIds: (ids) => {
    const prev = get().run.testCases;
    if (!prev) return;
    const run = touch({ ...get().run, testCases: { ...prev, selectedIds: ids } });
    // Selection is UI state: update the session run without rewriting recents.
    saveCurrent(run);
    set({ run });
  },

  setSuiteSummary: (summary) => {
    const run = touch({ ...get().run, suite: summary });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setAutomationPrefill: (scenarioPrefill, truncated) => {
    const run = touch({
      ...get().run,
      automation: { scenarioPrefill, truncated, updatedAt: nowIso() },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  setManualStory: (text) => {
    const current = get().run.criteria;
    const run = touch({
      ...get().run,
      criteria: { items: current?.items ?? [], source: 'manual', manualStory: text },
    });
    const recents = persist(run, get().recents);
    set({ run, recents });
  },

  adoptSharedRun: (shared) => {
    const now = nowIso();
    const run: Run = { ...shared, id: newId(), createdAt: now, updatedAt: now };
    const recents = persist(run, get().recents);
    set({ run, recents });
  },
}));
