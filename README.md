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

## Bug desk
Paste rough notes — *"checkout button does nothing on the second click, 3 of
5 tries"* — add the environment and attempt counts if you have them, and
optionally one screenshot, and the AI writes a structured report: title,
severity, numbered steps, actual against expected, plus workaround, suspected
pattern and investigation steps. **Report checks** is computed in code, not by
the AI: it scores the report out of seven — clear title, three or more steps,
actual and expected that differ, environment, reproducibility, evidence and a
real severity — and prints what to ask the reporter for whatever is missing.
Reproducibility and the environment line are counted from your inputs, so
*"Intermittent (3 of 5)"* is arithmetic, not a guess. **Copy as Markdown**,
**Copy for Jira** and **Download .md** give you the report in the form your
tracker wants, with Jira's markup characters escaped so a title full of
brackets cannot break the page. The screenshot is resized in your browser,
sent to your own provider with that one request and never stored; if the model
cannot read images, QA-Genius retries the same key with text alone and says so
on the card.

## Quality insights
Upload one to five test reports — JUnit XML (Playwright's
`--reporter=junit`, pytest's `--junitxml=report.xml`, Jest, Cypress or
Maven/Surefire all write it) or Playwright JSON (`--reporter=json`) — and
**Analyze**. No API key is needed for this: code reads the files and works out
the pass rate (skipped tests left out), groups the failures by a normalised
message so twenty timeouts with different millisecond values land in one
group, and finds the flaky tests — retried and passed, or passed in one run
and failed in another. **Explain with AI** is optional and sends only those
computed numbers and error messages to your provider, never the files
themselves, and every number on the page stays the one code computed; group
ids the AI invents are dropped with a note. Uploaded files are parsed in
memory for that one request with `defusedxml`, so an XML bomb or an external
entity is refused rather than expanded, and nothing is written to disk or
stored. **Draft bug report →** carries a failure group over to the Bug desk
with the notes prefilled.

## Troubleshooting
- `python scripts/check_key.py` checks one provider key with a tiny JSON
  request. It asks for the provider id and the key (hidden while typing)
  and prints `OK <provider> <model>` or the cleaned error. The key is
  never printed.
