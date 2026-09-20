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
app/            routes — (app) pages + /api/generate/[kind], /api/generators, /api/providers
components/     shell/ (sidebar, top bar), ui/ (design-system primitives), forms/, results/, generators/
lib/
  llm/          providers.ts (registry + tiers), byok.ts, generate.ts (stream/repair/re-ask), repair.ts, errors.ts
  generators/   one folder per kind: schema.ts (Zod), request.ts, prompt.ts (verbatim v1 port)
  prompts/      global-rules.ts (verbatim v1 GLOBAL_RULES etc.)
  exports/      csv, xlsx, feature, markdown, zip, json — all client-side
  client/       use-object-stream.ts (replaces the AI SDK useObject removed in ai v7), partial-JSON parser
  store/        zustand stores (keys, project) persisted to localStorage
fixtures/       Aurora Storefront demo data per kind (inputs + sample outputs)
tests/          unit (Vitest) · e2e (Playwright, mocked APIs) · live (opt-in)
scripts/        check-forbidden.mjs, check-hex.mjs, set-hooks.mjs
```

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
- **No server-side state** — no database, no file writes; run history arrives in Phase 4 via IndexedDB on the client.
- **Deterministic first** — counts, pass rates, and diffs are computed in code; the model only narrates.
- **Prompts are assets** — ported verbatim from v1 and frozen by snapshot tests in `tests/unit/prompts.test.ts`.

## Later phases

Requirements chaining + traceability (Phase 2) · automation compiles-clean + bug-desk GitHub integration (Phase 3) · quality insights parsing (Phase 4) · HAR → k6 performance (Phase 5) · launch + MCP + eval harness (Phase 6). See `AGENTS.md` §9.

## Live URL

Pending — import the repo in Vercel with root directory `web` and production branch `v2`.
