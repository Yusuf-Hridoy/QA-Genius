# NOTES — QA-Genius v2, Phase 1

Working decisions and version records. Mirrors `AGENTS.md` §9 (decisions) and §10 (deferrals).

## Installed versions (2026-09-19)

| Package                     | Version  | Note                                                                                                                                                          |
| --------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `next`                      | 15.5.25  | App Router, React 19.1                                                                                                                                        |
| `ai`                        | ^7.0.107 | v7 removed `useObject`; the client uses a custom hook (`lib/client/use-object-stream.ts`) that consumes the text stream and parses partial JSON progressively |
| `@ai-sdk/google`            | ^4.0.76  |                                                                                                                                                               |
| `@ai-sdk/groq`              | ^4.0.46  |                                                                                                                                                               |
| `@ai-sdk/openai`            | ^4.0.71  |                                                                                                                                                               |
| `@ai-sdk/anthropic`         | ^4.0.58  |                                                                                                                                                               |
| `@ai-sdk/openai-compatible` | ^3.0.53  | used for both OpenRouter and custom base URLs                                                                                                                 |
| `zod`                       | ^4.6.5   | v4 — `z.toJSONSchema` replaces the `zod-to-json-schema` package (still installed, unused)                                                                     |
| `xlsx-js-style`             | ^1.2.0   | replaces `xlsx` (SheetJS): supports bold/frozen/wrapped cells for the Test Cases sheet                                                                        |
| `jsonrepair`                | ^3.15.0  | fallback path in `lib/llm/repair.ts`                                                                                                                          |
| `zustand`                   | ^5.0.15  | persist → localStorage (`qag.keys.v1`, `qag.project.v1`)                                                                                                      |
| `shiki`                     | ^4.4.3   | `github-light-default` theme; gherkin rendered as plain text with a keyword tokenizer, not shiki                                                              |
| `lucide-react`              | ^1.47.0  | icon names differ from older versions (e.g. `FileArchive`, no `FileZip`)                                                                                      |
| `sonner`                    | ^2.0.8   | toasts                                                                                                                                                        |
| `vitest`                    | ^5.0.1   | with `@vitest/coverage-v8`                                                                                                                                    |

## Model ids verified against provider docs (2026-09-19)

- Gemini `gemini-2.5-flash-lite` / `gemini-2.5-flash` — current.
- Groq `llama-3.1-8b-instant` / `llama-3.3-70b-versatile` — current.
- OpenAI `gpt-4o-mini` for both tiers (Phase 1 default; revisit for a reasoning-tier model).
- Anthropic `claude-3-5-haiku-latest` / `claude-sonnet-4-5` — current.
- OpenRouter `google/gemini-2.5-flash-lite` / `google/gemini-2.5-flash` — current.
- OpenAI-compatible default `llama3.1` is a placeholder for local servers.

## Decisions taken during Phase 1 implementation

- **2026-09-19 — `useObject` replaced by a custom hook.** The installed AI SDK v7 no longer ships `experimental_useObject`; `lib/client/use-object-stream.ts` implements the same contract (progressive partial-JSON objects, stop, meta headers) over `fetch` + `ReadableStream`. The wire contract (§10–§11) is unchanged.
- **2026-09-19 — `xlsx-js-style` instead of `xlsx`.** The brief's "bold header, frozen, widths" needs cell styling; plain SheetJS cannot write styles.
- **2026-09-19 — git hooks without the husky runtime.** `husky` cannot locate `.git` from the `web/` subfolder in this monorepo layout; `scripts/set-hooks.mjs` (run by `prepare`) sets `core.hooksPath=web/.husky` directly. Husky dependency removed.
- **2026-09-19 — previous result retained on error.** `useObjectStream.submit` no longer clears the last object before a request; per §4.5 the previous result stays on screen when a generation fails.
- **2026-09-19 — hydration marker for e2e.** `AppShell` sets `data-hydrated` after mount so Playwright can wait for React event handlers before clicking (dev-mode SSR race); `waitForApp(page)` in `tests/e2e/helpers/stream-fixture.ts`.

## Deferred / parked

Mirrors `AGENTS.md` §10. Phase-1-specific items:

- **Vercel deploy + live-key verification (Checkpoints B and C).** The app builds clean and every API behavior is unit/e2e tested with mocks; importing the repo into Vercel (root `web`, branch `v2`) and running the four generators with real keys remains a manual step for the owner.
- **`zod-to-json-schema` package** remains installed but unused (Zod v4's built-in `z.toJSONSchema` is used instead). Kept for potential JSON-Schema draft differences; remove in a cleanup pass if still unused after Phase 2.
