---
name: qa-genius
description: Check QA work with QA-Genius. Use when the user gives a user story, acceptance criteria, test cases, risks or automation code and asks whether they are any good — "check this story", "review my test cases", "are these tests enough", "go QA-Genius", "check with QA-Genius". Also use before telling a user that testing for a story looks complete.
---

# QA-Genius

QA-Genius is a set of MCP tools that check QA work with plain code. There
is no AI and no API key behind them, so the same input always gives the
same answer and nothing you send is stored anywhere.

**You write the criteria, the tests, the risks and the code. QA-Genius
checks them.** It will not write a story for you and it will not tell you
a suite is finished — it tells you what is missing and what is wrong.

## The order

1. **`check_story`** — on the story as the team wrote it, before you draft
   anything. Fix the words it says nobody can test.
2. Write the acceptance criteria and the test cases yourself.
3. **`review_tests`** — fix every problem with `level: "high"`, then call
   it again. Repeat until no high problems come back.
4. Write the risks and score them, then **`score_risks`**. Add tests for
   every high risk with no test.
5. **`plan_matrix`** — when it matters which browsers, devices or roles
   the suite runs on.
6. **`check_code`** — if you wrote or changed automation.
7. **`ship_check`** — last. Give the user its `report_link`.

Steps 5 and 6 are skippable when the story does not call for them. Steps
1, 3 and 7 are not.

## Reading `problems`

Every tool answers in the same shape. `problems` is the list that matters,
worst first:

- **`level: "high"`** — fix these before you write anything else. A high
  problem usually means a test contradicts a criterion, a criterion has no
  test at all, or the story is really several stories.
- **`level: "medium"`** — fix before release.
- **`level: "low"`** — worth a look.

Each problem has a stable `id`. The same problem keeps the same id between
calls, so you can say "I fixed L-3f9a" and be understood.

`add_tests` holds ready-written tests, already in the shape `test_cases`
takes. Read them, keep the ones you agree with, and send them back in —
do not re-type them.

## `previous_report_link`

Every answer carries a `report_link`. Pass it back as
`previous_report_link` on your next call and the answer tells you:

- `fixed_since_last_check` — the ids that are gone
- `still_open` — the ids that are still there
- `not_checked_in_this_call` — ids another tool found, which this one does
  not look for

Use it on every call after the first. It is the only way the tools can
tell you whether your last round of fixes worked, because nothing is
stored between calls.

**Each tool is only ever compared against itself.** `ship_check` does not
look for duplicate tests, so it will never tell you one was fixed — it
puts those under `not_checked_in_this_call`. Do not read that as "fixed",
and do not tell the user it was: call `review_tests` again if you want to
know.

## Always do these

- **Show the user `ask_the_po`.** These are things no tool can decide —
  a limit nobody has written down, a risk somebody has to accept. Guessing
  at them is how a suite ends up testing the wrong number. Put them to the
  user in your own words and wait for an answer before assuming one.
- **Give the user the final `report_link`.** It opens a page showing the
  whole report. Nothing about it is stored on any server: the data is in
  the part of the URL after the `#`, which the browser never sends. Say
  that when you hand it over, so they know it is theirs to share or throw
  away.
- **Never say a check passed, or a problem was fixed, unless you ran the
  check that would find it.** In `ship_check`, a check with
  `status: "not_checked"` has *not* passed —
  it means you sent nothing for it. Three of the seven checks (story
  clarity, the two-reader comparison, automation) can only be run on the
  QA-Genius website and will always come back not checked from here. Say
  so rather than implying they are fine.
- **Use plain words with the user.** Say "no test covers AC-2", not "AC-2
  exhibits zero coverage".

## A worked example

The user pastes:

> As a shopper, I want to apply a discount coupon at checkout so that I
> pay less for my order. Coupons work on orders of at least $50.

**1. `check_story`** with that story. It comes back with the story reading
as one story and no untestable words — nothing to fix, so carry on.

**2.** You write three criteria and three tests. One criterion says "more
than $50", the context said "at least $50".

**3. `review_tests`.** Two high problems come back:

- `L-b225` — AC-1 covers "more than $50" and AC-2 covers "less than $50".
  Nobody says what happens at exactly $50.
- `L-b66f` — the context says "at least $50" but AC-1 says "more than $50".

Both are in `ask_the_po`, because only the product owner can settle them.
You put the question to the user, they say exactly $50 should work, you
fix AC-1, add a test at `cart_total=$50.00`, and take the tests from
`add_tests`.

**4. `review_tests` again**, with `previous_report_link` set to the link
from step 3. It comes back with `fixed_since_last_check: ["L-b225",
"L-b66f", …]` and no high problems.

**5.** You write four risks and call **`score_risks`**. One comes back
high with `coverage: "no test"`. You add a test for it.

**6. `ship_check`**, with `previous_report_link` from step 5. It answers
`decision: "Release with known risks"`, a grade, and a `report_link`.

**7.** You tell the user what was found and fixed, repeat the questions
they still have to answer, and give them the link.

## What the tools will not do

- They will not call an AI or use an API key. They are rules in code.
- They will not store your story, your tests or anything else. The logs
  hold counts and timings, never content.
- They will not tell you a suite is complete. "Nothing to fix" means the
  rules found nothing, not that the feature is safe.
