# AGENTS.md — QA-Genius v2

> **Read this file completely before writing a single line of code, in every phase, every session.**
> This is the single source of truth for the project. Phase briefs tell you *what to build this phase*; this file tells you *what the project is, how it is built, and the rules that never change*. If a phase brief and this file disagree, stop and ask — do not guess.
> At the end of every phase, update §9 (Phase log) and §10 (Deferred) in this file as part of the phase's definition of done.

---

## 1. What QA-Genius is

QA-Genius is a personal, open-source portfolio product by Yusuf Ahmed: an AI workspace for QA engineers that turns plain-language inputs (user stories, bug notes, HAR files, test reports) into structured, reviewable QA artifacts — and, unlike a chat window, **shows its evidence**: forks, scores, badges, diffs and real measurements instead of paragraphs.

**Identity line (use it in README, meta tags, demos):** *"The QA workspace that shows its evidence."*

**v1** (the code at the repo root) is a Python/Streamlit app with eight isolated tabs. It is being replaced, not refactored. It stays untouched on `main` until Phase 6 retires it into a `v1-streamlit` branch.

**v2** lives in `web/` and is what this file describes.

---

## 2. Non-negotiable rules

1. **BYOK only.** Users bring their own LLM key. The server has **no** LLM keys, no demo pool, no user database in Phases 1–5. A key is read from request headers, used for that one request, and discarded. It is never stored, logged, echoed, put in a URL, or included in an error. The only allowed representation in any log is `mask(key)` = first 4 + `…` + last 4. Every `/api/*` response sets `Cache-Control: no-store`.
2. **No employer, client, or workplace names anywhere** — not in code, fixtures, sample data, placeholders, tests, comments, screenshots, or docs. The fictional sample project is **Aurora Storefront** (Jira keys `AUR-####`, URL `staging.aurora-shop.dev`, SKUs `SKU-####`). CI greps for forbidden names and fails if any appear.
3. **Vercel Hobby limits are the architecture.** One Next.js project. Route handlers ≤ 300 s. No background jobs, no cron, no webhooks receivers, no runners, no long-lived processes, no server-side state between requests. Anything heavier is parked in §10.
4. **Deterministic first, LLM second.** Whenever a number can be computed (pass rates, p95, counts, coverage, diffs, parsing), compute it in code and let the model only narrate. Never let the model invent metrics.
5. **Prompts are assets.** The prompt text in `lib/prompts/` and `lib/generators/*/prompt.ts` was ported verbatim from v1 and is protected by snapshot tests. Change it only when a phase brief explicitly says so, and update the snapshot in the same commit with a one-line reason.
6. **Schemas are contracts.** Output schemas keep v1's field names and enums. Adding a field is fine; renaming or removing one needs a note in §9.
7. **No AI-tool tropes in the UI.** No gradients, no glows, no emoji, no purple-to-blue washes, no "✨ Magic" buttons. Lucide icons only. One accent-filled button per view.
8. **No self-incriminating code.** No `TODO fix later`, `placeholder`, `hack`, `temporary`. Unfinished = throw `NotImplementedError` and write it in §10.
9. **Tests are part of the feature.** A task without its acceptance test passing is not done. Unit coverage on `lib/**` ≥ 80%. E2E mocks `/api/*` via Playwright route interception; no test calls a real provider unless marked `live` and opt-in.
10. **Report back, don't self-certify.** Each phase ends with the report format in §11. Do not read files back, screenshot, or re-verify beyond what the brief's acceptance criteria require.

---

## 3. Stack (pinned — do not substitute without a §9 entry)

| Concern | Choice |
|---|---|
| Framework | Next.js 15, App Router, React 19 |
| Language | TypeScript 5, `strict: true`, no `any` |
| Package manager | pnpm (pinned via `packageManager`) |
| Styling | Tailwind CSS v4 + shadcn/ui, themed with the tokens in §4 |
| Fonts | `next/font/google`: Plus Jakarta Sans (display), Instrument Sans (body), JetBrains Mono (mono) |
| LLM | Vercel AI SDK (`ai`) + `@ai-sdk/google`, `@ai-sdk/groq`, `@ai-sdk/openai`, `@ai-sdk/anthropic`, `@ai-sdk/openai-compatible` |
| Schemas | Zod; `zod-to-json-schema` for the `/api/generators` contract |
| JSON repair | `jsonrepair` |
| Client state | React state; `zustand` (persisted to `localStorage`) for keys and project context; IndexedDB (`idb`) for run history from Phase 4 |
| Exports | `xlsx` (SheetJS), `jszip`, `papaparse` |
| Code display | `shiki` |
| Icons | `lucide-react` |
| Tests | Vitest + Testing Library; Playwright |
| Lint/format | ESLint (next + typescript-eslint), Prettier, husky + lint-staged |
| Hosting | Vercel Hobby, root directory `web`, production branch `v2` until Phase 6 |

**Why TypeScript and not Python (decision record):** one runtime and one deploy on Vercel; the AI SDK provides structured streaming across all providers in one call; streaming reaches React natively; the author's automation stack is Playwright TypeScript; simpler to explain. v1's prompts and schemas were ported verbatim so nothing of the prompt engineering was lost. Python is not coming back into `web/`.

---

## 4. Design system — look D "Cloud Dancer & Forest"

Chosen after seven rendered options. Light-only until dark mode is un-parked. All colors are CSS variables in `app/globals.css`, mirrored into Tailwind; **no raw hex in components** (CI greps for it).

```css
--bg:#F0EEE9; --side:#E7E4DD; --card:#FBFAF7; --card-2:#F3F1EC;
--border:#D9D5CC; --border-strong:#C8C3B8;
--text:#1B1F1C; --text-2:#555C56; --muted:#858C85;
--accent:#1F5E46; --accent-ink:#FFFFFF; --accent-soft:#DDEBE3;
--ok-bg:#DDEBE3; --ok-fg:#1F5E46;  --warn-bg:#F6E9CF; --warn-fg:#845708;
--bad-bg:#F7DEDA; --bad-fg:#9B3227; --info-bg:#E2E8F0; --info-fg:#354B6E;
--hl-bg:#F6E9CF; --hl-fg:#845708;
--radius:8px; --radius-card:12px;
```

Rules: cards `--card` + 1px `--border` + 12px radius; metric cards `--card-2`, no border; pills 11px/500, full radius, always a semantic bg/fg pair; sidebar 232px `--side`, active item `--card` bg + `--accent` text; headings and metric numbers in the display font (15/22/28px, 600); body 13–14px; mono 12px for IDs/code/keys; focus ring `0 0 0 3px var(--accent-soft)`; no shadows otherwise; body text contrast ≥ 4.5:1.

---

## 5. Product structure

Four workspaces in the sidebar. Everything else hangs off them.

| Workspace | Route | Contains (final state) |
|---|---|---|
| **Requirements** | `/requirements` | Story Analyzer (+ Ambiguity Duel) → Acceptance criteria → Test Cases (traceability, gap chips vs uploaded suite, refine with diff) → Automation (generate Playwright, compiles-clean check). Exports: CSV, XLSX, `.feature`, ZIP. Shareable result links. |
| **Bug desk** | `/bug-desk` | Bug Report from notes + screenshot/log drop; duplicate check against GitHub issues; create issue with the user's own token; Markdown export. |
| **Quality insights** | `/quality-insights` | Upload Playwright JSON / JUnit XML / `trace.zip`; deterministic metrics, run history, flaky detection; LLM narrative; drafted bugs with failure screenshots. |
| **Non-functional** | `/non-functional` | Performance: HAR → k6 (correlation, think-times, smoke/load/stress, SLO thresholds) → run locally → `result.json` → charts, outlier explanation, run comparison, drafted bug. Further NFR areas are parked (§10). |
| Settings | `/settings/keys` | BYOK key manager (add, test, default, delete), project context card. |

**Removed from v1 on purpose (do not re-add):** Schema Validator, Security Tests — they belong to the author's API-focused project, not here. The v1 Quality Analytics (prose in → numbers out) is replaced by Quality Insights (files in → computed numbers out).

---

## 6. Architecture map

```
web/
  app/                 routes (pages + /api route handlers)
  components/          shell/, ui/ (shadcn), forms/, results/, keys/
  lib/
    llm/               providers.ts (registry + tiers), byok.ts, generate.ts, repair.ts, errors.ts
    generators/        kinds.ts (registry) + one folder per kind: schema.ts, request.ts, prompt.ts
    prompts/           global-rules.ts (verbatim v1 GLOBAL_RULES etc.)
    exports/           csv.ts, xlsx.ts, markdown.ts, zip.ts
    parsers/           (Phase 4+) playwright-json.ts, junit.ts, trace-zip.ts, har.ts, k6-result.ts
    store/             keys.ts, project.ts (zustand, localStorage)
    utils/             mask.ts, cn.ts, id.ts
  fixtures/            golden inputs + sample outputs per kind (Aurora Storefront data)
  tests/unit, tests/e2e
```

**Request flow for any generator:**
`form → POST /api/generate/[kind] (BYOK headers) → validate kind + body → parseByok → buildPrompt → streamObject(model, zodSchema) → partial JSON stream → useObject in the client → cards render progressively → footer shows provider/model/tier/latency/request-id from response headers.`
Fallback: provider rejects structured output → `generateText` + `jsonrepair` + schema parse (`x-qag-repaired: 1`). Schema failure → one re-ask with the Zod error → then 502 `bad_model_output`.

**Adding a generator:** one folder in `lib/generators/<kind>/` (schema, request, prompt) + one registry entry in `kinds.ts` + a form and a result component. Nothing else.
**Adding a provider:** one entry in `PROVIDERS` in `lib/llm/providers.ts`.

**Error contract:** `{ error: code, message, details }` with codes `byok_required` 401, `invalid_key` 401, `unsupported_provider` 400, `content_blocked` 400, `validation_error` 422, `provider_rate_limited` 429 (+`retryAfter`), `bad_model_output` 502, `provider_unavailable` 503, `internal` 500. Messages are written for the user, never raw exceptions.

**Headers:** request `x-llm-provider`, `x-llm-key`, `x-llm-model?`, `x-llm-base-url?`; response `x-qag-provider`, `x-qag-model`, `x-qag-tier`, `x-qag-latency-ms`, `x-qag-request-id`, `x-qag-repaired?`.

**Model tiers:** every kind has a default tier, `fast` or `reasoning`; `PROVIDERS[p].defaultModels[tier]` resolves the model; a user override wins. Model ids are configuration in one file and may need updating — verify against provider docs when touched.

---

## 7. Generators — the registry

| kind | Workspace | Tier | Input (summary) | Output schema (v1 name) |
|---|---|---|---|---|
| `story_analyzer` | Requirements | fast | user story, context | `AmbiguityAnalysis` |
| `test_cases` | Requirements | fast | story/requirement, coverage focus, tech stack | `TestCaseList` |
| `automation_script` | Requirements | reasoning | test cases or story, framework, language, pattern | `AutomationScript` |
| `bug_report` | Bug desk | fast | raw notes, environment fields (+ screenshot from Phase 3) | `BugReport` |
| `quality_narrative` | Quality insights | reasoning | computed metrics JSON (Phase 4) | new |
| `performance_k6` | Non-functional | reasoning | parsed HAR + profile + SLA (Phase 5) | rebuilt from v1 `PerformanceTestSuite` |
| `performance_narrative` | Non-functional | fast | computed k6 metrics JSON (Phase 5) | new |
| `ping` | internal | fast | none | `{ ok: true }` |

Every request schema accepts `instructions?: string` (≤ 1000 chars) appended to the user prompt as `ADDITIONAL INSTRUCTIONS FROM USER:` — the refine loop uses it.

---

## 8. Conventions

- Files: `kebab-case.ts`; components `PascalCase.tsx`; one component per file.
- Server code never imports from `components/`; client code never imports `lib/llm/generate.ts`.
- All user-facing copy in sentence case, no exclamation marks, no "please", no "successfully".
- Empty states have a headline and one real sentence; never lorem ipsum.
- Commit messages: `phase-N: <area>: <what>` (e.g. `phase-1: llm: add provider registry`).
- Branch: all v2 work on `v2`; feature branches `v2/<topic>` merged by PR into `v2`.
- Fixtures are the demo data: every generator has `fixtures/<kind>/input-1.json` and `sample-output.json`, and the UI's "Load example" uses them.

---

## 9. Phase log  (update at the end of every phase)

| Phase | Scope | Status | Delivered / notes |
|---|---|---|---|
| 1 | Foundation: shell, look D, BYOK, provider layer, 4 generators, streaming, exports, tests, CI, live URL | **done** (2026-09-19, live URL pending owner deploy) | Full app in `web/`: shell + key manager + 4 generators streaming with repair/re-ask, client-side exports, 123 unit/component tests (87% stmts on lib/**), 21 e2e tests green, CI workflow. `pnpm check`, `build`, `e2e` green locally. Vercel import + real-key run (Checkpoints B/C) left to owner. |
| 2 | Requirements pipeline: chaining, traceability, Ambiguity Duel, refine with diff, share links, gap chips | planned | — |
| 3 | Automation compiles-clean; Bug desk multimodal, GitHub duplicate check + issue creation | planned | — |
| 4 | Quality insights: report/trace parsing, history, flaky detection, narrative, drafted bugs | planned | — |
| 5 | Non-functional: Performance (HAR → k6 → result.json analysis) | planned | — |
| 6 | Launch: eval harness, MCP endpoint, README/ARCH, demo video, retire v1 | planned | — |
| 7+ | NFR expansions (see §10) | to be discussed | — |

Decision records go here too, dated, one line each:
- 2026-09-19 — TypeScript-only on Vercel; Python backend dropped (reasons in §3).
- 2026-09-19 — Look D chosen from seven rendered options.
- 2026-09-19 — Schema Validator and Security Tests removed from scope (moved to the author's API project).
- 2026-09-19 — BYOK only; no demo key pool.
- 2026-09-19 — ai SDK v7 has no useObject; custom `use-object-stream.ts` client hook implements the same progressive-JSON contract.
- 2026-09-19 — `xlsx-js-style` replaces `xlsx` (cell styling for the Test Cases sheet).
- 2026-09-19 — git hooks set via `scripts/set-hooks.mjs` (`core.hooksPath=web/.husky`); husky runtime removed (monorepo layout).

---

## 10. Deferred / parked  (append; never silently drop)

Parked by decision (not Vercel-compatible or out of scope for now):
- Dark mode (tokens are structured to allow a `[data-theme="dark"]` block).
- Execution of generated tests in the user's own CI ("proof runs"), mutation testing, invariant monitors, drift detection via webhooks — all need runners or background jobs.
- Demo key pool / server-side keys.

Parked NFR expansions (to be discussed after Phase 5, in this order of likely value):
1. Web vitals and load — real LCP/INP/CLS via PageSpeed Insights API, field vs lab, "what to fix first".
2. Accessibility — Lighthouse a11y findings mapped to WCAG 2.2 + generated Playwright + axe-core regression test file.
3. SLO Forge — vague NFRs → measurable SLOs; Little's-law capacity math feeding the k6 config.
4. Compatibility matrix — browser/device/viewport targets → `playwright.config` projects.
5. Resilience scenarios — timeout, slow-3G, offline, 500s, expired token → route-mocking Playwright tests.
6. Localization stress — pseudo-localization (+30% length, RTL, Bengali/Arabic scripts) test set.
7. NFR scorecard — ISO 25010 categories, measured where possible, exportable PDF.

Agent-added deferrals (append below with phase and date):
- phase-1 (2026-09-19) — Vercel project import, production URL, and the Checkpoint B/C real-key verification run: the app is fully tested with mocks locally; deploying needs the owner's Vercel account.
- phase-1 (2026-09-19) — `zod-to-json-schema` package is installed but unused (Zod v4 `z.toJSONSchema` is used); revisit after Phase 2.

---

## 11. Phase report format  (paste this back at the end of each phase)

```
Phase N report
- Branch/PR: …
- Live URL: …
- CI run: …  (green/red)
- Unit coverage (lib/**): …%
- Providers tested live + resolved model names: …
- Acceptance criteria: N/N passed (list any failed)
- AGENTS.md updated: §9 row, decisions, §10 deferrals (yes/no)
- Deferred this phase: …
- Anything the next phase must know: …
```