# QA-Genius v2
FastAPI + HTMX rewrite of QA-Genius (v2 branch).
Old Streamlit app lives on `main` and is untouched.
Phase 1: sidebar, keys page, story check, load example.
Live URL: TBD

## Ambiguity duel
On Story check, **Run ambiguity duel** asks two AI readers (strict and
relaxed) to interpret the story separately, then compares them. Forks are
highlighted in the story text — hover or focus a highlight to see both
readings and a suggested rewrite. It uses 3 short AI calls. Both readers
must commit to concrete numbers with units for every vague word. A code
check removes any reading the comparison invents. Numbers from both
readers are matched by unit and name in code, so "same" and "different"
are computed, not guessed. Rewrites that are still vague are flagged and
can't be applied.

## Test cases
Requirements runs in three steps: **Story** check, **Acceptance criteria**,
then **Test cases**. The Use these criteria button carries the story and its
criteria to step 2, where you can edit, reorder, add and delete them; ids
stay AC-1..AC-n by position. Step 3 writes test cases from the story plus
those criteria, and each case shows the criteria it covers as AC chips. The
coverage meter, the per-category counts and the chips are all computed in
code from the ids each case lists, never read from the AI's own summary, so
an uncovered criterion is always reported. Download CSV or Excel for the
whole suite; the workbook adds a Coverage sheet and both formats quote any
cell that starts with = + - or @ so a spreadsheet cannot run it as a
formula. The run lives in your browser's sessionStorage only — the server
never stores it.

Coverage only says a criterion was touched, so the card also shows
**depth**: how many cases reach each criterion and whether any of them is
negative or boundary; a criterion with one happy-path case is marked thin.
**Strengthen thin criteria** asks the AI for just the missing kinds of case
and is additive by construction — code keeps every existing case exactly as
it was and drops any edit or deletion the AI attempted. **Refine…** takes an
instruction in your own words; either way the proposal arrives as a
before/after view with added, changed and removed cases counted in code,
which you can **Accept** or **Keep current**, and **Undo last change**
steps back through the last five accepted lists.

## Automation
Step 3 cards carry a checkbox, so you can tick up to twelve cases and hit
**Automate selected →** to reach step 4, where you choose a framework and
language (Playwright, Cypress or Selenium), Page Object Model or flat
scripts, the browsers to run, and an optional base URL. The AI writes the
project; code then checks it, as always. **Traceability** reports how many
of the selected cases have a test that names their id, listing any that do
not. Python files are parsed with `ast.parse`, so `valid` there means it
really parses; TypeScript and JavaScript only get a **basic check** that
brackets, quotes and comments balance — it is not a compile and not a type
check, and the result card says so. Any `waitForTimeout`, `time.sleep`,
numeric `cy.wait` or `Thread.sleep` is flagged as a fixed-wait warning with
its file and line. **Download ZIP** packs every file under one folder, with
a README carrying the setup steps, the run command and the same checks; the
file names the AI chose are cleaned first, so nothing can be written outside
that folder.

## Risk radar
**Risk radar** runs an FMEA over the current run: the AI lists the ways the
feature can fail in production — security, performance, reliability, data,
usability, accessibility and functional — and proposes a severity, likelihood
and detectability from 1 to 5 with a reason for each. Code does the rest: the
RPN is severity x likelihood x detectability, the level, the 5x5 heat map, the
counts and the order all come from that one formula, never from the model.
Coverage is checked rather than believed: a test case tagged `risk:R1` counts
as **verified**, a test case the AI claims is checked by word overlap and shows
as **covered** or, when the text does not match, as a **weak** link, and an id
the AI invented is dropped with a note. Adjust any score in the card and the
server recomputes everything, so the heat map and the order follow your
judgement. **Write tests for N untested high risks** sends those risks to step
3, where an additive refine writes cases tagged `risk:Rn` and shows them in the
usual Accept / Keep current / Undo view. **Download CSV** and **Download Excel**
give you the risk register, the Excel one with a Risk register sheet coloured by
level and a Heat map sheet.

## Ship check
**Ship check** answers one question — *can we ship this feature?* — and
answers it without an API key and without an AI call: every status is computed
by code from results the other desks already produced, using the same
functions those pages use, so Ship check can never disagree with the page you
just came from. Seven checks run over whatever your run holds: **story
clarity** (100 minus the ambiguity score), the **ambiguity duel** (agreement
and the worst fork), **criteria coverage** (any criterion with no test case
fails), **test depth** (thin criteria warn, more than half thin fails),
**risk coverage** (a high risk with no test fails, a medium risk with no test
or a high risk only weakly matched warns), **automation** (a syntax error
fails, a missing selected id or a fixed wait warns) and the **test matrix**
(a matrix that misses pairs or needs manual runs warns; it never fails). Each check is pass, warn, fail or *not
checked*, with the exact numbers behind it and a link back to the desk that
fixes it. The verdict follows in a fixed order: any fail means **Don't ship**;
otherwise a missing coverage or risk check means **Ship with risks**, because
there is not enough evidence to ship; otherwise any warning means **Ship with
risks**; and only a clean sweep is **Ship**. A failed check can be accepted
with a written reason of 10 to 300 characters — the acceptance is recorded on
the row, counts as a warning rather than a pass, and is removed again in one
click. **Copy as Markdown** gives you the whole verdict as a table with a
details section to paste into a release thread, and **Print / save as PDF**
prints the banner and every check with their details open, with the
sidebar, buttons and key chip left off the page.

## Test matrix
Browsers times devices times roles times languages is hundreds of combinations,
so teams test Chrome on a desktop and hope. *Pairwise* testing is the way out:
most environment bugs need only two things to coincide, so the smallest set of
runs where **every pair of values appears together at least once** finds them
without running everything — 216 combinations become 16 runs, and the page
proves it with *85 of 85 pairs covered*. QA-Genius proposes the factors that
matter for your story with a reason each (an AI reads the story; it never
decides a row), you add or remove factors, values and impossible combinations
such as *Firefox never on a phone*, and the matrix recalculates instantly in
code. Pin the runs you always want and they stay. **Download Playwright
config** gives you one project per automatable run with the right device
profile, locale, colour scheme and stored session, and **Download CSV** covers
the rest, including the runs Playwright cannot drive, which are counted rather
than quietly dropped. The result feeds the Test matrix row of Ship check.

## Also included (unlisted)
**Bug desk** (`/bugs`) turns rough notes and a screenshot into a structured
report with code-computed quality checks and Markdown/Jira exports, and
**Quality insights** (`/insights`) reads JUnit or Playwright reports with no
key at all, grouping failures and naming flaky tests. Both still work and are
still tested; they are simply not in the sidebar.

## Troubleshooting
- `python scripts/check_key.py` checks one provider key with a tiny JSON
  request. It asks for the provider id and the key (hidden while typing)
  and prints `OK <provider> <model>` or the cleaned error. The key is
  never printed.

## Development
- `pytest -q` runs the suite; `ruff check .` lints. Both must pass before a
  commit.
- `python scripts/ui_screenshots.py` saves a PNG of every desk at 1366×900
  and 390×844 into `ui-screens/` (git-ignored), so a UI change can be
  compared side by side instead of described. It starts nothing itself:

      pip install playwright          # a dev dependency, not in requirements.txt
      playwright install chromium
      uvicorn main:app --reload       # in one terminal
      python scripts/ui_screenshots.py   # in another

  Pass a different base URL as the one argument, e.g.
  `python scripts/ui_screenshots.py http://localhost:9000`. Every page is
  shot empty or through its own **Load example** button, so no API key is
  needed and no request reaches a provider.
