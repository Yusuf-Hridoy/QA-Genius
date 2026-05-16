# QA-Genius v1.1 — Improvement Brief for Kimi Code Agent

**Project:** QA-Genius (The SQA Intelligence Suite)
**Stack:** Python + Streamlit, multi-page app, Gemini 2.5 Flash Lite
**Code structure:** one Streamlit page per tab; one function per prompt in `prompts.py`
**Scope:** thorough refactor covering 7 tabs — Story Analyzer, Test Cases, Bug Report, Quality Analytics, Automation Script, Schema Validator, Security Tests, Performance Tests
**Goal:** fix the bugs and analytical gaps surfaced during a full review, lift each tab by at least one quality grade

---

## How to read this brief

- Tasks are tagged `[PROMPT]`, `[UI]`, or `[BOTH]`. Skip `[UI]` tasks last if time runs short — `[PROMPT]` work delivers most of the quality lift.
- Each task has an **acceptance criterion** — a specific, testable observation that confirms the change worked.
- File paths use placeholders like `pages/1_story_analyzer.py` — match them to actual filenames in the repo.
- `prompts.py` functions are referenced by assumed names (e.g., `build_story_analyzer_prompt()`) — match to actual function names.
- Do **not** widen scope beyond what's listed. Each task is scoped deliberately.

---

## SECTION 0 — GLOBAL RULES (apply to every prompt function in `prompts.py`)

These rules go into a shared section at the top of every prompt function. The cleanest implementation is a constant at the top of `prompts.py` that every function prepends to its prompt:

```python
GLOBAL_RULES = """
GLOBAL RULES — apply to every output you generate:

1. CLASSIFY EVERY VALUE you produce as one of:
   - DERIVED: lifted directly from the user's input
   - COMPUTED: derivable through stated math or logic from the input
   - UNKNOWN: cannot be determined from the input

2. NEVER present an UNKNOWN value as a fact. For UNKNOWN values you must:
   - Mark them with [VERIFY], [NOT PROVIDED], or [PLEASE CONFIRM], OR
   - Omit them entirely from the output

3. NEVER ship code or content with self-incriminating comments such as
   "placeholder, should be X", "TODO: replace this", "using displayed value
   for some reason", or any phrase admitting the value is wrong/guessed.
   If you cannot generate working content, list it under a "Limitations"
   section and explain what the user needs to provide.

4. NEVER hallucinate values that look plausible but aren't grounded in input
   (specific prices, version numbers, percentages, ID counts, dates, country
   codes, ISO codes, etc.). If a specific value is needed and not provided,
   use a partial assertion or placeholder.

5. BEFORE flagging any finding as a violation, explicitly verify:
   (a) the constraint, (b) the actual value, (c) whether the value
   satisfies the constraint. Only flag if the answer to (c) is "no". False
   positives are worse than missed findings — they erode trust in the
   entire report.

6. FOR EVERY NUMERICAL SCORE you produce, include a brief breakdown showing
   the components and weights used. Unexplained scores are forbidden.

7. READ THE INPUT TWICE before generating output. On the first read,
   identify every specific entity, technology, role, constraint, and
   context clue. On the second read, ensure your output references those
   specifics. Do not produce generic content that would apply to any
   project.

8. NEVER reference content from other tabs. Each tab is a self-contained
   analysis. Placeholder text shown in the UI is not user input — only
   treat the actual user input as data to analyze.
"""
```

**Task G1 — Add `GLOBAL_RULES` constant to `prompts.py` and prepend it to every prompt function** `[PROMPT]`
- Add the constant at the top of `prompts.py`
- Modify every `build_*_prompt()` function to start its returned prompt with `GLOBAL_RULES + "\n\n"`
- Acceptance: every prompt function's output begins with the global rules block

**Task G2 — Add a "Limitations" section requirement to every prompt** `[PROMPT]`
- Append to each prompt function's instructions: *"If any part of the output cannot be reliably generated from the input, list it under a final 'Limitations' section explaining what's missing and what the user should provide."*
- Acceptance: each tab's output has either real findings or an explicit Limitations section, never silently omits things

**Task G3 — Add a "Confidence per finding" instruction** `[PROMPT]`
- Add to each prompt: *"For every finding, classify confidence as HIGH (directly stated in input), MEDIUM (inferred from input), or LOW (general best practice not specific to this input). Display the confidence label on each finding."*
- Acceptance: each finding row in any tab includes a confidence label

---

## SECTION 1 — STORY ANALYZER

**Files:** `pages/1_story_analyzer.py`, `prompts.py::build_story_analyzer_prompt()`

### Input-side tasks

**Task SA-I1 — Add an optional "Project Context" field** `[UI]`
- Above the user story input, add an optional `st.text_area("Project Context (optional)", placeholder="e.g. fintech mobile app, B2B healthcare SaaS, internal tooling")`
- Pass this value into the prompt function as a separate parameter
- Acceptance: when a user provides project context, it appears in the prompt

**Task SA-I2 — Add an optional "Story Type" selectbox** `[UI]`
- Add `st.selectbox("Story Type", ["User Story", "Technical Story", "Bug Fix Story", "Spike/Research"])` with default "User Story"
- Pass into prompt; the analyzer should adjust INVEST evaluation based on type (technical stories often won't have a user-facing "Valuable" component)
- Acceptance: selecting "Technical Story" produces analysis that doesn't penalize lack of end-user value

### Output-side tasks

**Task SA-O1 — Fix Gherkin formatting** `[PROMPT]`
- Update prompt to require: *"Format every Gherkin scenario with an explicit `Scenario:` title on its own line, and place each Given/When/Then/And step on its own line with 2-space indentation under the Scenario title. Never concatenate steps into a single line."*
- Provide an example in the prompt:
  ```
  Scenario: Customer requests password reset with registered email
    Given a registered customer has forgotten their password
    When they navigate to the login page
    And they click "Forgot Password"
    And they enter their registered email address
    Then the system sends a password reset email within 1 minute
  ```
- Acceptance: generated Gherkin parses correctly in any standard Cucumber/Behave/SpecFlow runner

**Task SA-O2 — Add ambiguity score breakdown** `[PROMPT]`
- Update prompt to require a score breakdown table directly under the Ambiguity Score:
  ```
  | Component | Points |
  | Vague phrases | X |
  | Missing acceptance criteria | X |
  | INVEST failures | X |
  | Missing error scenarios | X |
  | Missing security/non-functional considerations | X |
  | Total | X/100 |
  ```
- Acceptance: every Story Analyzer output includes a score breakdown that sums to the displayed total

**Task SA-O3 — Require risk-to-scenario coverage** `[PROMPT]`
- Add to prompt: *"Every risk identified in the Risks section must have a corresponding Gherkin scenario in the Acceptance Criteria section, OR be explicitly listed in an 'Out of Scope' section with rationale."*
- Acceptance: no risk appears in the Risks section without either a Gherkin scenario or an Out of Scope entry

**Task SA-O4 — Add story splitting suggestion when Estimable fails** `[PROMPT]`
- Add to prompt: *"If INVEST 'Estimable' or 'Small' fails, include a 'Recommended Split' section listing 2-4 smaller stories that together cover the original."*
- Acceptance: when Estimable is marked Fail, output includes a Recommended Split section

**Task SA-O5 — Add security and notification scenarios for auth-adjacent stories** `[PROMPT]`
- Add to prompt: *"For stories involving authentication, password reset, account access, or PII, always generate Gherkin scenarios for: rate limiting, account-change notification email to the user, link/token expiry, link reuse prevention, and audit logging."*
- Acceptance: a password reset story produces at least 5 security-adjacent Gherkin scenarios

---

## SECTION 2 — TEST CASES

**Files:** `pages/2_test_cases.py`, `prompts.py::build_test_cases_prompt()`

### Input-side tasks

**Task TC-I1 — Add a "Test Coverage Focus" multiselect** `[UI]`
- Add `st.multiselect("Coverage Focus", ["Functional", "Negative", "Boundary", "Edge Case", "Accessibility", "Security", "Performance", "Localization"], default=["Functional", "Negative", "Boundary", "Edge Case"])`
- Pass selections into prompt; the prompt instructs the model to ensure coverage in each selected area
- Acceptance: selecting "Accessibility" produces at least 2 accessibility-focused test cases

**Task TC-I2 — Add a "Tech Stack" optional field** `[UI]`
- Add `st.text_input("Tech Stack (optional)", placeholder="e.g. React frontend + Node.js + PostgreSQL")`
- Pass into prompt; helps generate stack-aware test cases
- Acceptance: providing a stack generates technology-specific edge cases (e.g., PostgreSQL-specific cases for SQL inputs)

### Output-side tasks

**Task TC-O1 — Make Smoke and Regression multi-tags, not buckets** `[PROMPT]`
- Update prompt: *"Smoke and Regression are tags applied IN ADDITION TO the test design category (Functional/Negative/Boundary/Edge), not separate categories. Every test case has exactly one design category and zero or more execution tags. Mark 10-15% of cases as Smoke (covering critical happy paths and one critical negative). Mark 60-80% of cases as Regression-eligible (excluding only cases that test deprecated or one-time-use features)."*
- Update the output schema and UI display to show both design category and execution tags per test case
- Acceptance: a typical 20+ test case suite has 2-4 cases tagged Smoke and 12-16 cases tagged Regression-eligible

**Task TC-O2 — Force realistic automation feasibility distribution** `[PROMPT]`
- Update prompt: *"Mark 10-20% of cases as Manual-only or Low automation feasibility. Visual checks, exploratory cases, complex state validation, CAPTCHA flows, and accessibility checks requiring screen reader behavior are typically not High feasibility. A 100% High-feasibility output is unrealistic and will be rejected."*
- Acceptance: outputs with 20+ cases include at least 2-4 cases marked Medium, Low, or Manual-only feasibility

**Task TC-O3 — Define the Effort scale** `[PROMPT]`
- Add to prompt: *"For Effort estimation, use this scale: Low = under 1 hour, Moderate = 1-3 hours, High = over 3 hours. Display the scale in the output header so users understand the values."*
- Acceptance: every Test Cases output includes the effort scale legend

**Task TC-O4 — Add lifecycle and state test cases automatically** `[PROMPT]`
- Add to prompt: *"For features involving user input that persists (cart, draft, form, configuration), automatically generate test cases for: state after page refresh, state after browser close/reopen, state after session timeout, state after concurrent modification by another tab/session."*
- Acceptance: a discount code feature produces test cases like "apply code, refresh page, verify code state" and "apply code in tab A, modify cart in tab B, verify reconciliation"

**Task TC-O5 — Verify each test case has full detail** `[PROMPT]`
- Add to prompt: *"Every test case (not just the first) must include all sections: Pre-conditions, Steps (numbered), Expected Result, Test Data, BDD Scenario, Traceability, and Tags. Do not produce shallow placeholder cases — if a case can't be detailed, omit it."*
- Acceptance: spot-checking any 3 test cases shows the full structure, not collapsed/empty sections

---

## SECTION 3 — BUG REPORT

**Files:** `pages/3_bug_report.py`, `prompts.py::build_bug_report_prompt()`

### Input-side tasks

**Task BR-I1 — Add structured environment fields** `[UI]`
- Add a collapsible `st.expander("Environment Details (optional)")` containing:
  - `st.selectbox("Device Type", ["Not specified", "Desktop", "Mobile", "Tablet"])`
  - `st.text_input("OS / OS Version", placeholder="e.g. iOS 17.4, Windows 11, Ubuntu 22.04")`
  - `st.text_input("Browser / App Version", placeholder="e.g. Safari 17, Chrome 120, App v3.1.2")`
  - `st.text_input("Build / Environment", placeholder="e.g. Production, Staging, Build #1234")`
  - `st.text_input("URL where bug occurred")`
- Pass these into the prompt as structured data; if a field is "Not specified" or blank, the prompt must mark it as `[NOT PROVIDED]`
- Acceptance: leaving environment fields blank produces a Bug Report with `[NOT PROVIDED]` markers, not hallucinated values like "iOS 17.x"

**Task BR-I2 — Add an "Attempt Count" structured input** `[UI]`
- Add `st.number_input("Total attempts made", min_value=1, value=1)` and `st.number_input("Successful attempts", min_value=0, value=0)`
- Compute reproducibility automatically: if successful == 0, mark "Always". If successful > 0 and successful < total, mark "Intermittent" with the rate (e.g., "1 of 3"). If successful == total, prompt the user that this isn't a reproducible bug.
- Pass the computed reproducibility into the prompt
- Acceptance: 1 successful out of 2 attempts produces "Intermittent (1 of 2)" reproducibility, not "Always"

### Output-side tasks

**Task BR-O1 — Add no-hallucination rule for environment** `[PROMPT]`
- Add to prompt: *"Environment fields (OS version, build number, URL, browser version) must be filled ONLY with values explicitly provided by the user. If not provided, output `[NOT PROVIDED — please confirm before assigning]`. Never invent specific version numbers, build IDs, or URLs."*
- Acceptance: a bug report without an OS version specified shows `[NOT PROVIDED]` instead of "iOS 17.x"

**Task BR-O2 — Add "Suspected Pattern" classification** `[PROMPT]`
- Add to prompt: *"For every bug, include a 'Suspected Pattern' field with one of: Race Condition, Timeout, Session/Token Expiry, Network Flakiness, Third-Party Service Dependency, Logic Error, Validation Error, State Management Issue, Configuration Error, UI Rendering Issue. For intermittent bugs that succeed on retry, default to Race Condition or Timeout. State why the pattern was selected based on the symptom."*
- Acceptance: an intermittent checkout bug with retry success is tagged Race Condition or Timeout, with reasoning

**Task BR-O3 — Add "Related/Sub-Issues" section** `[PROMPT]`
- Add to prompt: *"If the bug description contains multiple distinct issues (e.g., a payment failure AND missing error feedback), include a 'Related Issues' section listing the secondary issues as candidates for separate tickets."*
- Acceptance: a bug report mentioning both "payment fails" and "no error shown" has Related Issues section with the missing-error-message as a separate candidate

**Task BR-O4 — Add "Investigation Steps" checklist** `[PROMPT]`
- Add to prompt: *"Replace generic suggestions like 'investigate further' with a concrete Investigation Steps checklist: console errors to check, network requests to inspect, server logs to query, third-party dashboards to verify, isolation tests to run (e.g., reproduce without the discount code applied to isolate whether the discount is the trigger)."*
- Acceptance: every bug report has a checklist of 4-6 concrete investigation actions, not vague advice

**Task BR-O5 — Component triage must list candidates, not assume** `[PROMPT]`
- Add to prompt: *"When triaging which component is at fault (Frontend / Backend / Database / Network / Third-party), list ALL plausible candidates with reasoning, never pick one without evidence. Mark as `[Component: Unknown — investigation required]` if multiple candidates apply equally."*
- Acceptance: a bug with ambiguous root cause shows multiple component candidates, not a confident single pick

---

## SECTION 4 — QUALITY ANALYTICS

**Files:** `pages/4_quality_analytics.py`, `prompts.py::build_quality_analytics_prompt()`

### Input-side tasks

**Task QA-I1 — Restructure the input as multiple fields** `[UI]`
- Replace the single textarea with a structured form:
  - `st.text_input("Sprint / Period Identifier")`
  - `st.number_input("Tests Passed")`, `st.number_input("Tests Failed")`, `st.number_input("Tests Blocked")`, `st.number_input("Tests Skipped")`
  - `st.text_area("Failure breakdown (one per line: area — count — root cause)", placeholder="checkout flow — 14 — discount code race condition\nsearch filters — 9 — new feature stabilization")`
  - `st.text_area("Blocker breakdown (one per line: count — reason — owner)")`
  - `st.text_area("Previous sprints data (optional)", placeholder="Sprint 16: 287 executed, 240 passed, 32 failed, ...")`
  - `st.text_area("MTTR by severity (optional)", placeholder="High: 3.2 days\nMedium: 6.8 days\nLow: 14 days")`
  - `st.number_input("QA team capacity (FTE-equivalent)", min_value=1.0, value=4.0, step=0.5)`
  - `st.number_input("Carryover bugs from previous sprints", min_value=0, value=0)`
- Pass each as a structured field; the prompt computes pass rate, defect density, and trend from these directly
- Acceptance: passing structured numeric inputs produces a report with mathematically correct pass rate (passed / total) and defect density (failed / total × 100)

### Output-side tasks

**Task QA-O1 — Compute and display trend table** `[PROMPT]`
- Update prompt: *"If multi-sprint data is provided (current + at least one previous sprint), produce a 'Sprint Trend' table comparing Pass Rate, Defect Count, Defect Density, and Top Failure Areas across the last 2-3 sprints. Explicitly flag escalating issues with the count progression (e.g., 'Checkout failures: 7 → 11 → 14 across last 3 sprints — escalating regression')."*
- Acceptance: providing 3 sprints of data produces a trend table with escalation callouts

**Task QA-O2 — No fabricated metrics** `[PROMPT]`
- Update prompt: *"Only report metrics that can be computed from the provided input. Do NOT include CI/CD Health, Coverage %, Velocity, Cycle Time, or other metrics unless the input contains supporting data. If a standard metric cannot be computed, explicitly state '[Not Available — not provided in input]'."*
- Acceptance: input without CI/CD data produces a report that does not include a CI/CD Health metric

**Task QA-O3 — Categorize failures by type** `[PROMPT]`
- Update prompt: *"Classify each failure area into one of: Product Bug (code defect), Environment Issue (infra, third-party flakiness), Test Flakiness (non-deterministic test), or New Feature Stabilization. Tailor recommendations and owners to the category — third-party flakiness goes to DevOps/Test Infra, not Dev."*
- Acceptance: SendGrid sandbox failures get a DevOps/Test Infra recommendation, not a Dev fix

**Task QA-O4 — Use severity-specific MTTR with benchmark comparison** `[PROMPT]`
- Update prompt: *"If MTTR data per severity is provided, display it in a table and compare against rough industry benchmarks (High: 1-3 days target, Medium: 3-7 days target, Low: 7-14 days target). Flag any severity exceeding its target as a process concern. Never reduce per-severity MTTR data into a single range."*
- Acceptance: providing High 3.2d / Medium 6.8d / Low 14d produces a table with each severity flagged or passing

**Task QA-O5 — Surface carryover bugs as a process concern** `[PROMPT]`
- Update prompt: *"If carryover bugs from previous sprints are reported, list them prominently in a 'Process Concerns' section. Carryover bugs of High severity that are 30+ days old must be flagged as critical escalation candidates."*
- Acceptance: input with "2 carryover High bugs from previous sprint" produces a Process Concerns section with escalation flag

**Task QA-O6 — Use team capacity context in recommendations** `[PROMPT]`
- Update prompt: *"If team capacity is provided and is below 100% (someone on leave, etc.), reference this context when explaining why blockers persisted or MTTR was elevated. Do not silently ignore capacity context."*
- Acceptance: input with "1 of 4 QA on leave" produces capacity-aware framing in the executive summary

**Task QA-O7 — Prioritize recommendations** `[PROMPT]`
- Update prompt: *"Order recommendations by impact, with the most urgent first. Three-sprint regressions are higher priority than single-sprint Safari-only bugs. Add a priority indicator (P0/P1/P2) to each recommendation."*
- Acceptance: recommendations are ordered by priority with explicit P0/P1/P2 labels

**Task QA-O8 — Add score rubric for Quality Health and Sprint Health** `[PROMPT]`
- Update prompt: *"Both Quality Health and Sprint Health scores must include a breakdown showing components and weights. Quality Health = product trajectory (defect trend, carryover, MTTR vs benchmark). Sprint Health = this sprint's execution (pass rate, blocker rate, capacity utilization). Each breakdown must sum to the displayed score."*
- Acceptance: every Quality Analytics output shows two distinct scoring rubrics with component breakdowns

---

## SECTION 5 — AUTOMATION SCRIPT

**Files:** `pages/5_automation_script.py`, `prompts.py::build_automation_script_prompt()`

### Input-side tasks

**Task AS-I1 — Make Language an explicit input** `[UI]`
- Add `st.radio("Language", ["JavaScript", "TypeScript"], index=0)` near the top of the form
- Pass selection into prompt; the prompt MUST honor it
- Acceptance: selecting JavaScript produces .js files with `require()` syntax, not TypeScript

**Task AS-I2 — Add a Structure selector** `[UI]`
- Add `st.radio("Structure", ["Flat scripts (no POM)", "Page Object Model"], index=0)`
- Default to flat scripts (matches Yusuf's team convention per memory)
- Acceptance: Flat scripts selection never produces POM directory structure

**Task AS-I3 — Add a Browser scope multiselect** `[UI]`
- Add `st.multiselect("Browsers", ["Chromium", "Firefox", "WebKit"], default=["Chromium"])`
- Pass into config generation
- Acceptance: only selected browsers appear in `playwright.config` projects

**Task AS-I4 — Add a Target Site Type field** `[UI]`
- Add `st.selectbox("Target Site Type", ["Custom (paste URL above)", "saucedemo.com", "the-internet.herokuapp.com", "automationexercise.com"])`
- When a known site is selected, the prompt loads a known-selectors hint for that site
- Acceptance: selecting saucedemo.com produces correct lowercase-hyphen `data-test` selectors

### Output-side tasks

**Task AS-O1 — Honor language selection strictly** `[PROMPT]`
- Update prompt: *"If the user selects JavaScript, produce ONLY .js files with `const { test, expect } = require('@playwright/test');` style imports, no type annotations, no `Page` type imports, no `.spec.ts` filenames, and `playwright.config.js` not `.ts`. Do NOT produce TypeScript when JavaScript is selected. This is a hard constraint."*
- Acceptance: selecting JavaScript produces zero `.ts` files and zero TypeScript syntax

**Task AS-O2 — Add known-site selector hints** `[PROMPT]`
- Add to prompt a knowledge block:
  ```
  Known site selectors (use these EXACTLY, lowercase-with-hyphens):
  saucedemo.com:
    - login: [data-test="username"], [data-test="password"], [data-test="login-button"]
    - product cards: [data-test="add-to-cart-sauce-labs-backpack"] (lowercase product name with hyphens)
    - cart: .shopping_cart_link, .shopping_cart_badge
    - inventory page header: .app_logo (contains "Swag Labs"), .title (contains "Products")
    - checkout: [data-test="checkout"], [data-test="firstName"], [data-test="lastName"], [data-test="postalCode"], [data-test="continue"], [data-test="finish"]
    - completion: [data-test="checkout-complete-header"], [data-test="checkout-complete-icon"]
  ```
- Acceptance: saucedemo scripts use lowercase-hyphen selectors and target `.app_logo` not `.title` for "Swag Labs" assertions

**Task AS-O3 — No hardcoded application data** `[PROMPT]`
- Update prompt: *"Never assert on specific prices, totals, counts, or IDs that depend on the target site's actual state. For amount/count assertions use partial patterns: `toContainText('$')`, `toMatch(/\\$\\d+\\.\\d{2}/)`, or compute the expected value from previously-extracted data. Never write a hardcoded value with a comment admitting you don't know it. The phrase 'using the displayed value' is forbidden."*
- Acceptance: no script contains hardcoded subtotals or "for some reason" comments

**Task AS-O4 — Modernize locator API** `[PROMPT]`
- Update prompt: *"Prefer modern Playwright locators in this priority order:
    1. `page.getByRole('button', { name: 'Login' })`
    2. `page.getByLabel('Username')`
    3. `page.getByPlaceholder('Username')`
    4. `page.getByTestId('username')` (for `data-testid` attributes)
    5. `page.locator('[data-test=\"username\"]')` (when site uses `data-test`, not `data-testid`)
    6. CSS selectors as last resort
  Avoid brittle CSS like `div > div > button:nth-child(3)`."*
- Acceptance: scripts default to role-based and label-based locators, fall back to attribute selectors only when needed

**Task AS-O5 — No unnecessary lifecycle hooks for single tests** `[PROMPT]`
- Update prompt: *"For a single `test()` block in a single file, do NOT add `beforeAll`/`afterAll` browser-lifecycle hooks. Playwright handles per-test browser context automatically. Only add lifecycle hooks if multiple tests share genuinely-mutable setup state (rare; should be justified in a comment)."*
- Acceptance: single-test scripts use plain `test('name', async ({ page }) => { ... })` without `let page: Page; beforeAll(...)`

**Task AS-O6 — Trust auto-waiting** `[PROMPT]`
- Update prompt: *"Use Playwright's auto-waiting via `expect()` and locator methods. Forbidden: `page.waitForTimeout(N)` and any `setTimeout` calls, except in narrowly justified cases (e.g., waiting for a known-debounced animation) where the timeout is documented with a comment explaining why."*
- Acceptance: scripts contain zero `waitForTimeout` calls in normal happy-path testing

**Task AS-O7 — Verifications use expect, never console.log** `[PROMPT]`
- Update prompt: *"Every verification step in the test plan must produce an `await expect(...)` assertion. `console.log()` is for debugging only, never for verification."*
- Acceptance: every numbered verification step in the input maps to an `expect()` call in the output

---

## SECTION 6 — SCHEMA VALIDATOR

**Files:** `pages/6_schema_validator.py`, `prompts.py::build_schema_validator_prompt()`

### Input-side tasks

**Task SV-I1 — Isolate placeholder text from actual input** `[UI]`
- Verify that the textarea's `placeholder` parameter is purely cosmetic and is NOT included when the field is empty. The current behavior appears to leak placeholder content (e.g., "email: null") into the analysis.
- If using Streamlit's `st.text_area`, the `placeholder` parameter is correctly cosmetic by default — but check that the prompt function is not concatenating placeholder text into the LLM input
- Acceptance: submitting the form with the actual input shown in the screenshots produces a report that does NOT mention "email is null" when the actual email field contains a valid string

**Task SV-I2 — Add a "Validation Layers" multiselect** `[UI]`
- Add `st.multiselect("Validation Layers", ["Structural (types, formats)", "Semantic (business rules)", "Security (sensitive data, PII)"], default=["Structural (types, formats)", "Semantic (business rules)", "Security (sensitive data, PII)"])`
- Pass into prompt to scope what's checked
- Acceptance: deselecting "Security" produces a report without security findings

### Output-side tasks

**Task SV-O1 — Add explicit pass/fail reasoning gate** `[PROMPT]`
- Update prompt: *"For each field, before flagging it as a violation, internally walk through:
    (a) What is the constraint?
    (b) What is the actual value?
    (c) Does the value satisfy the constraint? Yes or No?
  ONLY include findings where (c) is No. If the value satisfies the constraint, do NOT flag it. False positives erode trust in the entire report — better to miss a finding than fabricate one. After generating the findings list, re-read each one and remove any where the Expected and Actual fields demonstrate the value actually passes."*
- Acceptance: a value of `1247` for "must be positive integer" is NOT flagged. A value of `"admin"` against enum `[user, admin, moderator]` is NOT flagged. A value of `28` against range 18-120 is NOT flagged.

**Task SV-O2 — Add ground-truth knowledge for standardized formats** `[PROMPT]`
- Add to prompt a knowledge block:
  ```
  Standard format references (verify against these before flagging):
  - ISO 3166-1 alpha-2 country codes: BD (Bangladesh), US (United States), GB (United Kingdom), etc. — always 2 uppercase letters; verify the specific code is on the official ISO list before flagging
  - ISO 639-1 language codes: en, es, fr, de, ja — always 2 lowercase letters
  - E.164 phone format: +[country code][number], digits only after the +, max 15 digits total. Examples of VALID E.164: +12125551212, +8801712345678, +442012345678
  - RFC 5322 email format: local-part@domain.tld where domain has at least one dot. Example domains like example.com, example.org, example.net are valid
  - UUID format: 8-4-4-4-12 hex digits separated by hyphens
  - ISO 8601 date-time: YYYY-MM-DDTHH:MM:SSZ or with timezone offset
  ```
- Acceptance: BD, +8801712345678, and yusuf@example.com are NOT flagged as invalid

**Task SV-O3 — Deduplicate findings** `[PROMPT]`
- Update prompt: *"After generating all findings, perform a deduplication pass: if two findings target the same field with the same constraint, keep only one. Each field-constraint pair appears in the output exactly once."*
- Acceptance: no two findings have the same Path AND the same Constraint

**Task SV-O4 — Verify "missing field" findings against actual payload** `[PROMPT]`
- Update prompt: *"Before flagging a field as 'missing', confirm by re-reading the payload that the field is genuinely absent. Fields present in the payload, even with null or empty values, are NOT 'missing' — they are present-with-null and require a different finding type if problematic."*
- Acceptance: a payload containing `"refresh_token": "abc123"` does NOT produce a "refresh_token is missing" finding

**Task SV-O5 — Compliance score with breakdown** `[PROMPT]`
- Update prompt: *"The compliance score must include a breakdown:
    - Structural integrity: X/Y points
    - Semantic correctness: X/Y points
    - Security posture: X/Y points
    - Total: sum/total displayed
  The total must mathematically equal the sum of the breakdowns. Any number you cannot derive from the components must be omitted."*
- Acceptance: Compliance Score 14/100 is replaced by a breakdown showing how 14 was reached

**Task SV-O6 — Severity must match impact** `[PROMPT]`
- Update prompt: *"Severity rubric:
    - Critical: PII/credentials exposure (password, SSN, credit card, internal tokens), authentication bypass, RCE
    - High: type mismatches affecting business logic, missing required fields, broken authorization
    - Medium: format violations, naming inconsistencies, exposed metadata
    - Low: cosmetic, missing optional fields, soft conventions
  Never assign Critical to non-security issues like 'value is in allowed enum' or 'integer is positive'."*
- Acceptance: only PII/security/auth findings are Critical; structural type mismatches are High at most

**Task SV-O7 — Add findings the tool currently misses** `[PROMPT]`
- Update prompt to explicitly check for:
  - Refresh token in response body (security smell — should be HttpOnly cookie)
  - Test data leaking to production-shaped responses (e.g., "fake_signature" in JWT)
  - Mixed snake_case and camelCase field naming as a single inconsistency finding
  - Optional vs required field handling (omitting optional fields is valid, not a violation)
- Acceptance: a payload with `refresh_token: "abc123"` in body produces a Medium-severity finding about token storage location

---

## SECTION 7 — SECURITY TESTS

**Files:** `pages/7_security_tests.py`, `prompts.py::build_security_tests_prompt()`

### Input-side tasks

**Task ST-I1 — Expand Authentication options** `[UI]`
- Replace JWT/OAuth2 single selection with multiselect `st.multiselect("Authentication", ["JWT", "OAuth2", "SAML SSO", "API Keys", "Session Cookies", "Basic Auth", "mTLS"])`
- Pass each selected mechanism into the prompt
- Acceptance: selecting SAML produces SAML-specific tests (XML signature wrapping, assertion replay, XXE)

**Task ST-I2 — Expand Sensitive Features chips** `[UI]`
- Add to the multiselect: "Authentication", "File Upload", "Admin/RBAC", "Third-party APIs", "Search/Enumeration", "Webhooks", "Public Marketing Site (shared origin)", "Multi-Tenancy"
- Each adds specific test categories to the prompt
- Acceptance: selecting "Multi-Tenancy" produces cross-tenant IDOR tests

**Task ST-I3 — Add a "Compliance Context" multiselect** `[UI]`
- Add `st.multiselect("Compliance Context", ["HIPAA (Healthcare)", "PCI-DSS (Payments)", "GDPR (EU users)", "COPPA (Children)", "SOC 2", "None / Not Sure"])`
- Pass into prompt; the prompt generates compliance-specific tests beyond OWASP
- Acceptance: selecting HIPAA produces PHI-aware tests (PHI in URLs, audit log integrity, export controls)

**Task ST-I4 — Add an "Infrastructure" text field** `[UI]`
- Add `st.text_area("Infrastructure & Hosting (optional)", placeholder="e.g. AWS EKS, Cloudflare CDN, no WAF, secrets in AWS Secrets Manager")`
- Pass into prompt for infrastructure-aware findings
- Acceptance: input mentioning "no WAF" produces a Critical infrastructure finding flagging the missing WAF

### Output-side tasks

**Task ST-O1 — Generate technology-specific injection tests** `[PROMPT]`
- Update prompt with this rule: *"For each technology mentioned in the application description, generate technology-specific tests rather than generic SQLi:
    - PostgreSQL/MySQL/SQL Server → SQL injection with stack-specific payloads
    - MongoDB → NoSQL injection (operator injection like {\"$ne\": null}, JSON injection)
    - Redis → command injection if user input reaches Redis keys
    - Elasticsearch → Elasticsearch query injection
    - LDAP → LDAP injection
  If MongoDB is mentioned and you do not generate at least one NoSQL injection test, you have failed this requirement."*
- Acceptance: an app description mentioning MongoDB produces at least one NoSQL injection test case with `{"$ne": null}`-style payloads

**Task ST-O2 — Generate cross-tenant IDOR tests for multi-tenant apps** `[PROMPT]`
- Update prompt: *"If the application is multi-tenant (B2B SaaS, white-label, organization-scoped data), generate at least 3 cross-tenant IDOR tests targeting different resource types. Specify the test as: authenticate as User_A in Tenant_A, then attempt to access resource_id belonging to Tenant_B. Expected: 403 or 404, never the resource data."*
- Acceptance: a multi-tenant healthcare app produces tests like "ClinicAdmin from Clinic A attempts GET /api/patients/{id_in_clinic_B}"

**Task ST-O3 — Generate privilege escalation matrix for stated roles** `[PROMPT]`
- Update prompt: *"If the application defines explicit roles (e.g., SuperAdmin, Admin, User), generate a privilege escalation matrix as a separate test category. For N roles, generate at least N-1 vertical escalation tests (lower role attempts higher-role action) and 1-2 horizontal escalation tests (same role attempts another instance's data)."*
- Acceptance: an app with 4 roles produces at least 3 vertical escalation tests as distinct test cases

**Task ST-O4 — Read infrastructure context for findings** `[PROMPT]`
- Update prompt: *"Scan the application description for infrastructure mentions: WAF, CDN, hosting provider, secrets management, encryption at rest. For each MISSING security control explicitly stated as missing (e.g., 'no WAF configured'), generate a Critical infrastructure finding in a 'Critical Infrastructure Gaps' section."*
- Acceptance: input containing "No WAF currently configured" produces a Critical finding flagging missing WAF

**Task ST-O5 — Generate compliance-specific tests** `[PROMPT]`
- Update prompt: *"If compliance context is selected:
    - HIPAA: PHI in URLs/logs, audit log integrity (especially if MongoDB stores audit logs — test for tamper detection), export controls, role-based PHI access, encryption at rest verification
    - PCI-DSS: card data in logs, tokenization verification, scope minimization
    - GDPR: right-to-erasure verification, consent tracking, data residency
    - COPPA: age verification, parental consent flow, data collection limits
  Each compliance context adds 3-5 dedicated test cases beyond OWASP."*
- Acceptance: HIPAA selection produces at least 4 healthcare-compliance-specific tests

**Task ST-O6 — Stack-relevant tests only** `[PROMPT]`
- Update prompt: *"Only include test cases applicable to the specified stack. Do NOT generate classic insecure deserialization tests for Node.js/Express unless the description mentions known-vulnerable libraries (node-serialize, etc.). Do not generate Java-specific deserialization for Python apps. Match the test catalog to the stack."*
- Acceptance: a Node.js + Express app does NOT produce a generic "Insecure Deserialization of Patient Data Objects" finding without justification

**Task ST-O7 — Stripe webhook inbound testing** `[PROMPT]`
- Update prompt: *"If a Stripe webhook endpoint is mentioned, generate inbound webhook tests: signature validation bypass (request without `Stripe-Signature` header), webhook replay (same signed payload sent twice — should be rejected via idempotency), timestamp tolerance (Stripe rejects timestamps older than 5 minutes), forged payload rejection."*
- Acceptance: any app with a Stripe webhook endpoint produces these 4 webhook-specific tests

**Task ST-O8 — File upload depth** `[PROMPT]`
- Update prompt: *"If file upload is in scope, generate tests for: file type bypass (MIME confusion, polyglot files, double extensions), size limit bypass, path traversal in filenames, antivirus scanning verification, stored XSS via SVG, S3 pre-signed URL abuse (long expiration, reusable URLs, URLs in logs), PII in filenames if PII context is selected."*
- Acceptance: a healthcare app with file upload produces a "PHI in filenames" test under HIPAA context

**Task ST-O9 — CSV injection for export endpoints** `[PROMPT]`
- Update prompt: *"If the application includes CSV export of user-controlled data, generate a CSV injection test (formula injection: `=cmd|'/c calc'!A1`, `+cmd`, `-2+3+cmd`, `@SUM(...)`) targeting the export endpoint."*
- Acceptance: a "patient data export as CSV" feature produces a CSV injection test

**Task ST-O10 — SMS pumping fraud for SMS providers** `[PROMPT]`
- Update prompt: *"If a SMS provider integration is mentioned (Twilio, MessageBird, etc.), generate a SMS pumping fraud test: attacker triggers many SMS to attacker-controlled premium numbers to exhaust the company's SMS budget. The relevant defense is rate limiting on SMS-triggering endpoints and phone number validation. Do NOT generate command-injection-via-SMS tests — Twilio's API doesn't typically allow that."*
- Acceptance: a Twilio integration produces an SMS pumping fraud test, NOT a command injection test

---

## SECTION 8 — PERFORMANCE TESTS

**Files:** `pages/8_performance_tests.py`, `prompts.py::build_performance_tests_prompt()`

### Input-side tasks

**Task PT-I1 — Make Peak Events selection meaningful** `[UI]`
- Replace single-chip selection with `st.selectbox("Peak Event Type", ["Daily Peak", "Black Friday / Flash Sale", "Live Event Spike", "Cron Job Spike", "Marketing Campaign Launch", "Custom"])`
- For "Custom", add a free-text field for ramp shape description
- Pass into prompt; each event type produces a distinctly shaped load profile
- Acceptance: Black Friday produces a sharp 5-10x ramp sustained 1-2 hours, Daily Peak produces a 4-6 hour bell curve

**Task PT-I2 — Add a "Per-endpoint SLA" structured input** `[UI]`
- Add a section where users specify per-endpoint SLAs as rows: endpoint name + p95 target + p99 target (optional)
- Pass as a list into the prompt
- Acceptance: per-endpoint SLAs in input produce per-endpoint thresholds with correct k6 tag syntax

**Task PT-I3 — Add an "Output Configuration" multiselect** `[UI]`
- Add `st.multiselect("Metrics Output", ["Console only", "InfluxDB + Grafana", "Prometheus remote write + Grafana", "k6 Cloud", "JSON file"], default=["InfluxDB + Grafana"])`
- The selection determines what config files/snippets the output includes
- Acceptance: selecting "InfluxDB + Grafana" produces both the k6 output flag config AND a Grafana dashboard JSON

### Output-side tasks

**Task PT-O1 — Working correlation everywhere** `[PROMPT]`
- Update prompt: *"For every chained request that depends on a previous response (product_id from browse, access_token from login, cart_id from add-to-cart, order_id from checkout), extract the value from the response and pass it to the next step. NEVER use `Math.random() * N` as a placeholder for a real ID. NEVER ship code with a comment like 'should be correlated' or 'placeholder'. If correlation requires a response field that may not exist, use defensive checks: `const productIds = res.json('products')?.map(p => p.id) || [];` then guard the next step on the array being non-empty."*
- Acceptance: no generated k6 script contains `Math.random() * 100000` for an ID, no `// placeholder, should be correlated` comments

**Task PT-O2 — Per-endpoint thresholds must match request tags** `[PROMPT]`
- Update prompt: *"When generating per-endpoint thresholds using the `{name:X}` selector, you MUST also tag the corresponding request with `tags: { name: 'X' }` in its options object. Verify before output that every threshold tag is applied to at least one request, and every named request has a corresponding threshold (or is intentionally untagged). The format MUST match exactly:
    Threshold:  'http_req_duration{name:Login}': ['p(95)<500']
    Request:    http.post(url, payload, { headers: {...}, tags: { name: 'Login' } })"*
- Acceptance: every threshold with a `{name:X}` selector has a matching `tags: { name: 'X' }` on a request

**Task PT-O3 — Correct k6 metric semantics** `[PROMPT]`
- Update prompt: *"For RPS / throughput SLA assertions, use `rate>X` not `count>X`. For total request count, use `count>X`. The k6 metric `http_reqs` supports both — pick the right one for the assertion type. For RPS targets, also consider asserting `iterations` rate. Verify your math: `count` is cumulative, `rate` is per-second."*
- Acceptance: an SLA of "throughput > 2000 RPS" produces `http_reqs: [{ threshold: 'rate>2000' }]`, never `count>2000`

**Task PT-O4 — Threshold abort logic must be coherent** `[PROMPT]`
- Update prompt: *"For multi-threshold setups (e.g., 0.5% SLA breach + 2% hard abort): the lower threshold (SLA) MUST have `abortOnFail: false`, the higher threshold (auto-abort) MUST have `abortOnFail: true`. As written, an abortOnFail at 0.5% kills the test before the 2% threshold can engage. The user's intent is: 'breach SLA = note it, hit hard ceiling = abort'."*
- Acceptance: the 0.5% threshold has `abortOnFail: false`, the 2% threshold has `abortOnFail: true`

**Task PT-O5 — Remove invented k6 parameters** `[PROMPT]`
- Update prompt: *"Use only documented k6 threshold options: `threshold` (the expression), `abortOnFail` (boolean), `delayAbortEval` (string duration). Do NOT invent parameters like `delay`. Do NOT invent k6 functions. If unsure whether a k6 API exists, omit it rather than fabricate."*
- Acceptance: no generated script contains undocumented k6 parameters like `delay: '10s'`

**Task PT-O6 — Six load profiles with distinct executors** `[PROMPT]`
- Update prompt: *"Generate exactly 6 load profiles in `options.scenarios`, each with the appropriate k6 executor:
    - Smoke: ramping-vus, low VUs, short duration
    - Average Load: ramping-vus, target VUs, sustained
    - Stress: ramping-vus, 2-3x target VUs, sustained
    - Spike: ramping-vus, 5-10x target VUs, very sharp ramp (1-2 minutes), short sustained, fast ramp-down
    - Soak: constant-vus or ramping-vus, target VUs, multi-hour sustained
    - Breakpoint: ramping-arrival-rate or ramping-vus, gradual ramp until failure
  Use different `exec` function names if profiles need different behavior, but if behavior is shared, all can `exec: 'default'`."*
- Acceptance: all 6 profiles exist as distinct scenarios with different stages/executors

**Task PT-O7 — Peak event-specific spike shape** `[PROMPT]`
- Update prompt: *"The Spike scenario shape MUST match the Peak Event input:
    - Black Friday / Flash Sale: ramp 0 → peak in 1-2 minutes, sustain 60-120 minutes, decay 30-60 minutes
    - Daily Peak: bell curve over 4-6 hours
    - Live Event: instant spike, sustain event duration, sharp drop
    - Cron Job Spike: instant peak at fixed intervals (use `ramping-arrival-rate` for repeated spikes)
  Do not generate an identical spike shape regardless of event type."*
- Acceptance: switching Peak Event from Daily Peak to Black Friday produces a visibly different scenario.spike configuration

**Task PT-O8 — Generate Grafana dashboard config when requested** `[PROMPT]`
- Update prompt: *"When 'InfluxDB + Grafana' or 'Prometheus + Grafana' is in Output Configuration:
    1. Include the k6 run command with the correct `--out` flag
    2. Include a Grafana dashboard JSON OR reference an official k6 community dashboard ID (2587 for InfluxDB, 18030 for Prometheus, 19665 for k6 Cloud)
    3. Include panel definitions for: VU count, RPS, p95 response time per endpoint, error rate, iteration duration
    4. Include alerting rule examples tied to the SLA thresholds
  Do NOT promise a Grafana dashboard and then omit it. If the dashboard JSON is too long, include the import command for the official dashboard ID and a brief panel customization guide."*
- Acceptance: every output with InfluxDB+Grafana selected includes either a dashboard JSON or a community dashboard ID with import command

**Task PT-O9 — Provide CSV example for parameterization** `[PROMPT]`
- Update prompt: *"When the script uses SharedArray to load user credentials from a CSV, ALSO output a sample CSV (5-10 rows) showing the expected structure (header + sample data). Include in the run instructions how to generate test users in the target system or a note: 'CSV must contain users that exist in the staging environment.'"*
- Acceptance: every Performance Tests output includes a sample `users.csv` with header and example rows

**Task PT-O10 — Auth header on authenticated requests only** `[PROMPT]`
- Update prompt: *"Anonymous endpoints (browse, search, public pages) must NOT include the Authorization header. Authenticated endpoints (cart, checkout, user-specific GET) MUST include it. Do not blanket-apply auth headers to every request."*
- Acceptance: anonymousBrowseFlow has no Authorization header; addToCartFlow does

---

## SECTION 9 — VERIFICATION CHECKLIST

After all changes, run each tab with the same inputs used in the original review (preserved in this brief's Appendix A) and verify these specific issues are resolved:

**Story Analyzer:**
- [ ] Gherkin scenarios have explicit `Scenario:` headers and proper indentation
- [ ] Ambiguity score includes a component breakdown
- [ ] Risks are matched to Gherkin scenarios or Out-of-Scope entries
- [ ] Password reset story produces rate limiting, notification email, link reuse, and audit log scenarios

**Test Cases:**
- [ ] Smoke tag count is non-zero (not 0/25)
- [ ] Regression tag count is non-zero
- [ ] Automation feasibility distribution is realistic (not 100% High)
- [ ] No content from other tabs (no password reset references when input is about discount codes)

**Bug Report:**
- [ ] Environment fields show `[NOT PROVIDED]` when not given, not "iOS 17.x"
- [ ] Reproducibility correctly classified as Intermittent for "1 of 2 attempts" inputs
- [ ] Suspected Pattern field present (Race Condition / Timeout for retry-success bugs)
- [ ] Investigation Steps are concrete, not vague

**Quality Analytics:**
- [ ] Three-sprint trend table appears when 3 sprints provided
- [ ] CI/CD Health metric does NOT appear when not in input
- [ ] Failure categorization distinguishes product bugs from environment flakiness
- [ ] MTTR shown per severity, not as single range
- [ ] Carryover bugs appear in Process Concerns
- [ ] Quality Health and Sprint Health each have score breakdowns

**Automation Script:**
- [ ] JavaScript selection produces .js files, not .ts
- [ ] saucedemo selectors are lowercase-with-hyphens
- [ ] No hardcoded subtotal values; assertions use partial patterns
- [ ] No `waitForTimeout` calls
- [ ] `.app_logo` is used for "Swag Labs" assertion, not `.title`
- [ ] No self-incriminating comments

**Schema Validator:**
- [ ] `1247` is NOT flagged as "not a positive integer"
- [ ] `"admin"` is NOT flagged as outside `[user, admin, moderator]`
- [ ] `28` is NOT flagged as outside 18-120 range
- [ ] `BD` is NOT flagged as invalid ISO country code
- [ ] `+8801712345678` is NOT flagged as invalid E.164
- [ ] `yusuf@example.com` is NOT flagged as invalid email
- [ ] `refresh_token: "abc123"` is NOT flagged as missing
- [ ] Compliance score has a breakdown
- [ ] No duplicate findings (same field + same constraint)
- [ ] Severity rubric is enforced (no Critical for type mismatches)

**Security Tests:**
- [ ] Multi-tenant input produces cross-tenant IDOR tests
- [ ] MongoDB input produces NoSQL injection test
- [ ] "no WAF" in description produces Critical Infrastructure Gap finding
- [ ] HIPAA context produces 4+ healthcare-specific tests
- [ ] Stripe webhook produces 4 inbound webhook tests
- [ ] Twilio produces SMS pumping test, not command injection
- [ ] Insecure deserialization is NOT generated for Node.js without justification
- [ ] CSV export feature produces CSV injection test

**Performance Tests:**
- [ ] No `Math.random() * 100000` placeholders
- [ ] No `// placeholder, should be correlated` comments
- [ ] All correlations work (product_id, jwt, cart_id, order_id all chained)
- [ ] Per-endpoint thresholds have matching `tags: { name: 'X' }` on requests
- [ ] RPS threshold uses `rate>X`, not `count>X`
- [ ] Threshold abort logic is correct (0.5% no-abort, 2% abort)
- [ ] No `delay` parameter in thresholds
- [ ] 6 distinct load profiles with different executors/stages
- [ ] Black Friday spike has different shape than Daily Peak
- [ ] Grafana dashboard config or community ID included
- [ ] Sample users.csv included
- [ ] Auth headers only on authenticated endpoints

---

## SECTION 10 — APPENDIX A: VERIFICATION INPUTS

These are the exact inputs used in the original review. Re-run each tab with these to verify fixes.

### Story Analyzer
> "As a customer, I want to be able to reset my password easily so that I don't get locked out of my account."

### Test Cases
> "Feature: Cart checkout with discount codes. Users can apply one discount code per order. Codes can be percentage-based (e.g., 10% off) or fixed-amount (e.g., $5 off). Codes have expiry dates and minimum order values. Some codes are single-use per user. Invalid, expired, or already-used codes should show an error."

### Bug Report
> "checkout broken on mobile. tried 3 times. iphone 14, safari. cart had 2 items, applied SAVE10 code, clicked pay, page just spins forever. no error. tried again worked second time. screenshot attached (pretend)."

### Quality Analytics
The full Sprint 17 input from the review (312 tests, 248 passed, 41 failed, 18 blocked, with three-sprint history, MTTR per severity, capacity context, carryover bugs).

### Automation Script
The 14-step saucedemo purchase flow with explicit JavaScript / flat scripts / Chromium-only / role-based locators / no waitForTimeout requirements.

### Schema Validator
The healthcare-style API response with 24 planted issues (password, SSN, credit_card exposure; duplicate Email/email; type mismatches; valid values like "admin" and `BD` that should NOT be flagged).

### Security Tests
The multi-tenant healthcare SaaS description (PostgreSQL + Redis + MongoDB, JWT/OAuth2/SAML, four roles, Stripe Connect, S3, Twilio, no WAF).

### Performance Tests
The 8-endpoint chained user journey with explicit correlation requirements, per-endpoint SLAs, six load profiles, and Black Friday peak event.

---

## SECTION 11 — IMPLEMENTATION ORDER (suggested)

If working sequentially through tabs, this order minimizes rework:

1. **Section 0 — Global Rules** (foundation; everything else builds on this)
2. **Schema Validator** (worst false-positive rate; biggest credibility risk)
3. **Automation Script** (executable bugs; objectively measurable)
4. **Performance Tests** (executable bugs + missing Grafana; objectively measurable)
5. **Quality Analytics** (analytical depth; restructure inputs)
6. **Bug Report** (hallucination fix + new structured fields)
7. **Story Analyzer** (formatting + scoring + minor)
8. **Test Cases** (already strong; mostly tag and feasibility refinements)
9. **Security Tests** (already strong; architectural-signal refinements)

Test each tab with its verification input from Appendix A before moving to the next.

---

## END OF BRIEF

Total tasks: 78 across 8 sections (excluding Global). Estimated effort: full day to 1.5 days for an autonomous coding agent.

For any task where the brief is ambiguous or your codebase doesn't match the assumed structure, stop and ask before proceeding. Do not silently widen scope.
