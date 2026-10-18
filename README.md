# QA-Genius v2
FastAPI + HTMX rewrite of QA-Genius (v2 branch).
Old Streamlit app lives on `main` and is untouched.
Phase 1: sidebar, keys page, story check, load example.
Live URL: TBD

## Two-reader check
On Story check, **Run the two-reader check** asks two AI readers — one
strict, one loose — to read the story separately, then compares them. The
places they disagree are marked in the story text. Hover or focus a mark to
see both readings and better wording. It uses 3 short AI calls. Both readers
have to give a real number with a unit for every unclear word. Code then
removes any reading the comparison invented. The numbers are matched by name
and unit in code, so "same" and "different" are worked out, not guessed.
Wording that is still unclear is flagged and cannot be used.

## Test cases
Requirements runs in three steps: **Story** check, **Acceptance criteria**,
then **Test cases**. The Use these criteria button carries the story and its
criteria to step 2, where you can edit, reorder, add and delete them; ids
stay AC-1..AC-n by position. Step 3 writes test cases from the story plus
those criteria, and each case shows the criteria it covers as AC chips. The
coverage meter, the counts by kind and the chips are all worked out in code
from the ids each case lists, never read from the AI's own summary, so a
criterion with no test is always reported. Download CSV or Excel for the
whole suite; the workbook adds a Coverage sheet and both formats quote any
cell that starts with = + - or @ so a spreadsheet cannot run it as a
formula. The run lives in your browser's sessionStorage only — the server
never stores it.

Being tested at all is not the same as being tested well, so the card also
shows **how well tested** each criterion is: how many tests reach it, and
whether any of them tries wrong input or sits at a limit. A criterion with one
happy-path test is marked *needs more tests*, and the line above says what is
really missing — *"5 of 5 criteria need more tests — 4 have no test for wrong
input, 1 has only one test."* **Add more tests where needed** asks the AI for
just the missing kinds of test and can only add: code keeps every existing
test exactly as it was and drops any edit or deletion the AI tried. **Change
with your own instruction…** takes a sentence in your own words. Either way
the answer arrives as a before/after view with added, changed and removed
tests counted in code, which you can **Accept** or **Keep current**, and
**Undo last change** steps back through the last five lists you accepted.

## Automation
Step 3 cards carry a checkbox, so you can tick up to twelve cases and hit
**Automate selected →** to reach step 4, where you choose a framework and
language (Playwright, Cypress or Selenium), Page Object Model or flat
scripts, the browsers to run, and an optional base URL. The AI writes the
project; code then checks it, as always. The card says how many of the tests
you picked have a test that names their id, and lists any that do not. Python
files are read by a real parser, so *it parses* there means exactly that.
TypeScript and JavaScript only get a **quick code check** that brackets,
quotes and comments match — it is not a compile and not a type check, and the
card says so. Any `waitForTimeout`, `time.sleep`, numeric `cy.wait` or
`Thread.sleep` is flagged as a **fixed pause**, with its file and line,
because a fixed pause makes tests slow and flaky. **Download ZIP** packs every file under one folder, with
a README carrying the setup steps, the run command and the same checks; the
file names the AI chose are cleaned first, so nothing can be written outside
that folder.

## Risk radar
**Risk radar** lists the ways this feature can break in production — security,
performance, reliability, data, usability, accessibility and plain broken
behaviour — and gives each one three scores from 1 to 5, with a reason: how bad
it is, how likely it is, and how hard it is to notice. Code does the rest. The
risk score is how bad × how likely × how hard to notice, and the level, the
5×5 risk map, the counts and the order all come from that one sum, never from
the model. Whether a test covers a risk is checked, not believed: a test tagged
`risk:R1` was written for it; a test the AI names is checked on shared words
and shows as *probably tested*, or, when the words do not match, as a doubt the
page states plainly; and an id the AI invented is dropped with a note. A risk
QA-Genius added itself knows the words that mean it is tested, so *"System
prevents email enumeration"* is matched to the enumeration risk without anyone
tagging anything. Change any score in the card and the server works it all out
again, so the map and the order follow your judgement. **Write tests for N high
risks with no test** sends those risks to step 3, where an add-only change
writes tests tagged `risk:Rn` and shows them in the usual Accept / Keep current
/ Undo view. **Download CSV** and **Download Excel** give you the risk
register, the Excel one with a register sheet coloured by level and a risk map
sheet.

## Ship check
**Ship check** answers one question — *can we release this feature?* — with no
API key and no AI call. Code works out every line from results the other desks
already produced, using the same functions those pages use, so Ship check can
never disagree with the page you just came from. Seven checks run over whatever
your run holds: **how clear the story is** (100 minus the unclear score), the
**two-reader check** (how far apart the readers were, and the worst
disagreement), **criteria with a test** (any criterion with no test fails),
**how well tested** (criteria needing more tests warn; more than half fails),
**risks with a test** (a high risk with no test fails; a medium risk with no
test, or a high risk matched only by a few shared words, warns), **automation**
(a code error fails; a missing id or a fixed pause warns) and the **test
matrix** (a matrix that misses pairs or needs runs by hand warns; it never
fails). Each check is *fine*, *have a look*, *needs fixing* or *not done yet*,
with the numbers behind it and a link back to the desk that fixes it. The
decision follows in a fixed order: anything needing fixing means **Not ready**;
otherwise a missing coverage or risk check means **Release with known risks**,
because there is not enough to go on; otherwise any warning means **Release
with known risks**; and only a clean sweep is **Ready to release**. A failed
check can be accepted with a written reason of 10 to 300 characters — the
reason is kept on the row, counts as a warning rather than a pass, and is
removed again in one click. **Copy as Markdown** gives you the whole decision
as a table to paste into a release thread, and **Print / save as PDF** prints
the banner and every check with its detail open, leaving the sidebar, the
buttons and the key chip off the page.

## Test matrix
Browsers times devices times roles times languages is hundreds of runs, so
teams test Chrome on a desktop and hope. There is a way out: most setup bugs
need only two things to meet, so the smallest set of runs where **every two
options are tested together at least once** finds them without running
everything — 216 combinations become 16 runs, and the page proves it with *85
of 85 pairs covered*. QA-Genius suggests the things worth varying for your
story, with a reason for each (an AI reads the story; it never decides a run).
If the AI forgets Browser or Device, code puts them back, because almost every
story is a screen. You then add or remove things to vary, their options, and
combinations that can't happen such as *Firefox never on a phone*, and the
matrix works itself out again at once, in code. Mark the runs you always want
with **Always keep** and they stay. **Download Playwright config** gives you
one project per run a tool can drive, with the right device, language, colour
scheme and saved sign-in, and **Download CSV** covers the rest, including the
runs Playwright cannot drive, which are counted rather than quietly dropped.
The result feeds the Test matrix row of Ship check.

## The senior tester
Every AI call on every desk has a senior tester sitting either side of it, and
it costs you nothing: same click, same single AI call, no key of its own, no
waiting. **Before** the call, QA-Genius adds a short list of what a senior
tester would insist on for this kind of feature — the email typed in capitals,
the same error for an unknown email and a wrong password, the file of exactly
5 MB and the one a byte over — along with the exact numbers your criteria imply
(4 / 5 / 6 attempts, 14 / 15 / 16 minutes). **After** the call it reads what
came back and adds what is still missing, straight into the same result: tests
labelled **Added by senior tester** with the reason they exist and a Remove
button, extra risks scored by the same rules as the AI's own, notes on
automation code that never checks anything or leaves `.only` behind, and a
warning on Story check when a story is really seven features in a trench coat.
It never changes the AI's own work — it only adds, and everything it adds can
be removed, with Undo. All of it is plain Python over rule packs, so it runs on
**Load example** with no key at all.

A check that is only about one narrow thing — the language an email is written
in, rounding a second currency — carries `only_if` and waits until your story
raises that subject, so a lockout story is never asked for a test about
languages.

The rules live in `qagenius/shadow_qa/packs/*.toml`, one file per kind of
feature, and you can add your own — drop a file in and it is picked up. A pack
wakes up on one `trigger`, a word only its kind of feature uses. Words half the
stories in the world contain — *email*, *list*, *file*, *admin* — go in
`weak_triggers` instead, and it takes two different ones to wake the pack: one
of them on its own, anywhere, is ignored. Where a word was said still counts
for order, so packs your story names out loud are offered before packs found
only in the criteria.

```toml
id = "coupons"
name = "Coupon codes"
short = "Coupons"
triggers = ["coupon", "coupons", "promo code", "discount code"]
weak_triggers = ["voucher", "discount"]

[[checks]]
id = "expired"
title = "An expired coupon is refused"
severity = "high"
why = "An expired code that still works gives money away."
covered_if = ["expired", "expiry", "no longer valid"]
only_if = []          # optional: use this check only when the story says one of these
  [checks.test]
  title = "Apply a coupon one day after it expired"
  category = "Negative"
  priority = "High"
  pre_conditions = "A coupon SPRING10 expired yesterday"
  steps = ["Add an item to the basket", "Apply SPRING10 and read the message"]
  expected_result = "The coupon is refused with a message saying it has expired, and the total is unchanged."
  test_data = "code=SPRING10"
```

## Always up to date
Every desk says, at the top, what it was built from and whether that is still
your latest work: **Not built yet**, **Old — your work changed** or **Matches
your latest work**, each with an icon and words, so the state never rests on
colour alone. The card
names the change in numbers — *"Your criteria changed 3 min ago (4 → 5)"* —
and its button is the page's one primary action, so there is never a second
button competing with it. Work that code can redo updates by itself: Risk
radar re-scores coverage against your newest test cases, and Ship check
recomputes on every open and marks any input that lags behind. Anything that
would spend your AI key waits for a click. The sidebar carries the same
answer as an amber dot or a green tick, so you know before you click.

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

## Plain words
Every word on a screen is meant to be readable by a tester in their first
month, or by one whose first language is not English: short sentences,
everyday words, and no QA jargon standing in for an idea. The few standard
words that stay — acceptance criteria, test case, at the limit, wrong input,
INVEST, risk score, Playwright, given/when/then — carry a small ⓘ that says
what they mean. Those notes live in one place, `public/plain_words.js`, and a
template reaches one with `data-explain="boundary"`. Exports keep the standard
QA words, because a CSV goes to a tool, not to a reader. Every AI call also
asks for plain English, so the text that comes back reads like the rest.
`tests/test_plain_words.py` renders every page and fails if a word from the
banned list reaches a screen.

## Development
- `pytest -q` runs the suite; `ruff check .` lints; `node --test tests/js`
  runs the browser-side unit tests. All three must pass before a commit.
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
