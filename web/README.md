# QA-Genius v2

**The QA workspace that shows its evidence.** QA-Genius turns plain-language inputs — user stories, bug notes, requirements — into structured, reviewable QA artifacts: scored stories, categorized test cases, formatted bug reports, and runnable automation scaffolds, with streaming results and deterministic metrics.

This is the v2 rewrite of the Streamlit app in the repo root (v1). Everything lives in this folder; v1 stays untouched on `main` until Phase 6.

## BYOK — bring your own key

QA-Genius has no server-side keys and no demo key pool. You add an API key in Settings, it is stored only in your browser's `localStorage`, and each generation request sends it to your chosen provider through this app's server — which never stores or logs it. Delete a key any time. Free keys:

- [Google Gemini](https://aistudio.google.com/app/apikey)
- [Groq](https://console.groq.com/keys)
- [OpenRouter](https://openrouter.ai/keys)
- [OpenAI](https://platform.openai.com/api-keys)
- [Anthropic](https://console.anthropic.com/settings/keys)
- Any OpenAI-compatible URL (Ollama, LM Studio, vLLM)

## Local setup

```bash
cd web
pnpm install        # Node 20, pnpm 9 (see .nvmrc / packageManager)
pnpm dev            # http://localhost:3000
```

## Scripts

| Command                     | What it runs                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `pnpm check`                | lint + format check + typecheck + unit tests (with coverage) + forbidden-names + no-raw-hex |
| `pnpm test`                 | Vitest with `lib/**` coverage                                                               |
| `pnpm e2e`                  | Playwright (Chromium); mocks every `/api/generate/*` route                                  |
| `pnpm build` / `pnpm start` | Production build / serve                                                                    |
| `pnpm format`               | Prettier write                                                                              |

Git hooks (set on `pnpm install` via `scripts/set-hooks.mjs`): pre-commit runs lint-staged; pre-push runs typecheck + unit tests.

Live smoke tests against a real provider are opt-in: `LIVE_PROVIDER=gemini LIVE_KEY=... pnpm exec playwright test tests/live`.

## Folder map

```
app/            routes — (app) pages + /api/generate/[kind], /api/generators, /api/providers, /share
components/     shell/ (sidebar, top bar), ui/ (design-system primitives), forms/, results/, generators/
                requirements/ (stepper, criteria editor, coverage, duel), diff/, refine/, share/, suite/
lib/
  llm/          providers.ts (registry + tiers), byok.ts, generate.ts (stream/repair/re-ask), repair.ts, errors.ts
  generators/   one folder per kind: schema.ts (Zod), request.ts, prompt.ts (verbatim v1 port)
  duel/         story_interpretation + duel_compare internal kinds, run-duel.ts, highlights.ts
  pipeline/     Run type, step helpers, automation prefill, autosubmit keys
  traceability/ AC-n parsing and coverage computation (deterministic)
  diff/         test-case and story revision diffs (deterministic)
  share/        URL-fragment codec (deflate + base64url) and shared-run parsers
  suite/        CSV/XLSX parsing, IndexedDB storage, deterministic matcher
  prompts/      global-rules.ts (verbatim v1 GLOBAL_RULES etc.)
  exports/      csv, xlsx, feature, markdown, zip, json — all client-side
  client/       use-object-stream.ts (replaces the AI SDK useObject removed in ai v7), partial-JSON parser, generate-one.ts
  store/        zustand stores (keys, project, run) — keys/project in localStorage, run in sessionStorage + recents
fixtures/       Aurora Storefront demo data per kind (inputs + sample outputs) + suite/aurora-suite.csv/.xlsx
tests/          unit (Vitest) · e2e (Playwright, mocked APIs) · live (opt-in)
scripts/        check-forbidden.mjs, check-hex.mjs, set-hooks.mjs
```

## Requirements pipeline

The Requirements workspace is a four-step pipeline with one shared run (`sessionStorage`, recent runs in `localStorage`): **Story → Acceptance criteria → Test cases → Automation**. Switching steps never loses data; New run clears it.

- **Story** — the analyzer plus paste/example source picker, the Ambiguity Duel, a refine loop with diff, share links, and a handoff that copies generated acceptance criteria into step 2 as `AC-1..n`.
- **Acceptance criteria** — editable list with drag reorder (ids recompute from order), add/delete, and a from-scratch story box when there is no step 1. Generate test cases injects the criteria into the prompt and auto-submits step 3.
- **Test cases** — the form collapses into a summary bar; cards carry AC traceability chips and a coverage metric (`AC covered n/total`) with a recovery path for uncovered criteria; checkboxes prefill the Automation scenario; refine, share, and existing-suite gaps live here too.
- **Automation** — the scenario arrives prefilled from the selected cases (truncated at 5 000 characters with a note).

### Ambiguity Duel

Two blind readings of the story (strict vs permissive, temperature 0.8) are diffed by a third call (temperature 0.2) into forks and agreements. Vague phrases are highlighted inline in the story with tooltips; readings sit side by side; each fork offers a suggested rewrite that can be applied to the story. Costs 3 short model calls; agreement ratio and highlights are computed in code.

### Refine with diff

Test cases and the story analysis can be revised with instructions (1 000 chars). Revisions are diffed deterministically — id match first, then title similarity (token Jaccard ≥ 0.6), steps by array LCS, words by word diff — and shown with added/changed/removed/unchanged pills plus a changes-only filter. Accept pushes the old output to history (undo supported for test cases); exports always use the accepted version.

### Share links

Share buttons encode the run into the URL fragment (`JSON → deflate → base64url`), so `/share#…` renders read-only with no server storage and no keys. Links show their size, warn past 64 KB, and refuse past 200 KB. Open in my workspace adopts the run with a fresh id.

### Existing suite gaps

Upload a `.csv`/`.xlsx` suite (client-side parse, column mapping with preview, stored in IndexedDB, capped at 5 000 rows). Each generated case is matched deterministically (weighted token Jaccard, title × 2; covered ≥ 0.55, similar 0.35–0.55, gap below) and badged covered/similar/gap, with a covered/new metric, a gaps-only filter, and gaps-only CSV/XLSX export.

## Add a generator

1. `lib/generators/<kind>/` with `schema.ts`, `request.ts`, `prompt.ts` (port the v1 prompt verbatim).
2. One entry in `lib/generators/kinds.ts`.
3. A form in `components/forms/`, a result in `components/results/`, an export bar, and a `GENERATOR_UI` entry in `components/generators/registry.ts`.
4. Fixtures (`input-1.json`, `sample-output.json`) and snapshot/round-trip tests.

## Add a provider

One entry in `PROVIDERS` in `lib/llm/providers.ts` (display name, key-help URL, default models per tier) plus a case in `createModel`. Model ids are configuration — verify them against the provider's docs when touching this file.

## Decisions

- **TypeScript only, on Vercel** — one runtime, one deploy; v1's Python backend is retired (see repo-root `AGENTS.md`).
- **Vercel AI SDK with structured streaming** — one `streamObject` call per provider; fallback to `generateText` + `jsonrepair` when a provider rejects JSON-schema mode (`x-qag-repaired: 1`), then one re-ask with the Zod issues.
- **BYOK only** — keys in `x-llm-*` request headers, read once per request, never stored or logged; the only allowed log form is `mask(key)`.
- **No server-side state** — no database, no file writes; the run lives in sessionStorage, recent runs in localStorage, suite rows in IndexedDB.
- **Deterministic first** — counts, pass rates, traceability, highlights, matches, and diffs are computed in code; the model only narrates.
- **Prompts are assets** — ported verbatim from v1 and frozen by snapshot tests in `tests/unit/prompts.test.ts`. Phase 2 appends only user-prompt blocks (criteria, previous) and adds new duel prompts with their own snapshots.

## Later phases

Requirements pipeline, duel, refine, share, and suite gaps (Phase 2, done) · automation compiles-clean + bug-desk GitHub integration (Phase 3) · quality insights parsing (Phase 4) · HAR → k6 performance (Phase 5) · launch + MCP + eval harness (Phase 6). See `AGENTS.md` §9.

## Live URL

Pending — import the repo in Vercel with root directory `web` and production branch `v2`.
