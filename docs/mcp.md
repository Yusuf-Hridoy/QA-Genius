# QA-Genius for AI agents

QA-Genius has a second door. As well as the website, it runs an **MCP
server** at `/mcp`, so Claude — in Claude Code, the Claude app, Cowork or
on a phone — can call its checks directly.

The split is the point:

- **Claude writes.** The acceptance criteria, the test cases, the risks,
  the automation code. All of it.
- **QA-Genius checks.** With the same plain Python the website runs:
  senior-tester rules, limit checks, depth per criterion, risk scoring,
  the pairwise matrix, the ship decision.

**No AI call. No API key. Nothing stored.** Every tool is rules in code,
so the same input always gives the same answer, and the website and an
agent can never disagree about the same story — they run the same
functions.

---

## Connect it

**Claude Code**

```
claude mcp add --transport http qa-genius https://qa-genius-ashy.vercel.app/mcp
claude mcp list
```

**Claude app · Cowork**

Customize → Connectors → Add custom connector → paste
`https://qa-genius-ashy.vercel.app/mcp`.

There is nothing to sign in to and no key to paste. A `404` means `/mcp`
is switched off on that deployment — see **Turning it on** below.

There is also a skill in `integrations/claude/qa-genius/` that tells
Claude when to reach for these tools and in what order.

---

## The order to call them in

1. **`check_story`** — before anything is written. Fix the words nobody
   can test.
2. Write the criteria and the tests.
3. **`review_tests`** — fix every `high` problem, call again, repeat until
   none come back.
4. Write the risks, then **`score_risks`**. Add tests for high risks with
   no test.
5. **`plan_matrix`** — which browsers, devices and roles to run on.
6. **`check_code`** — if automation was written.
7. **`ship_check`** — last. Hand the user its `report_link`.

Every tool is read-only (`readOnlyHint`, `idempotentHint`,
`openWorldHint: false`). Nothing it is sent is executed, and nothing is
written anywhere.

---

## The answer shape

Every tool answers with the same fields, so an agent that can read one can
read all six:

```json
{
  "schema_version": "1.0",
  "tool": "review_tests",
  "summary": "6 to fix · 5 criteria · 14 tests",
  "problems": [
    {
      "id": "L-3f9a",
      "kind": "limit",
      "level": "high",
      "says": "AC-1 covers \"more than $50\" and AC-2 covers \"less than $50\". Nobody says what happens at exactly $50.",
      "fix": "Decide the number and write it into a criterion.",
      "criteria": ["AC-1", "AC-2"],
      "tests": []
    }
  ],
  "add_tests": [ "...TestIn-shaped, ready to send back in..." ],
  "ask_the_po": ["..."],
  "notes": ["..."],
  "report_link": "https://.../report#v1.…",
  "fixed_since_last_check": [],
  "still_open": []
}
```

`ship_check` adds `decision`, `grade`, `checks` and `path_to_ready`.
`score_risks` adds `risks` and `untested_high`. `plan_matrix` adds `runs`
and the pair counts. `check_code` adds `syntax`, `findings` and the
traced test case ids.

**Problem ids are stable.** An id is the first letter of its kind plus
four hex of a hash of what the problem is about — not where it sat in a
list. The same problem keeps the same id between calls, so an agent can
say "I fixed `L-3f9a`" and be understood.

---

## The report link, and rounds

Every answer carries a `report_link`:

```
https://qa-genius-ashy.vercel.app/report#v1.<packed>
```

`<packed>` is the answer plus what the page needs to show it, as JSON →
raw deflate → base64url. **It is after the `#`, which a browser never
sends**, so the server has not seen the report it is about to draw and has
nothing to store or to forget. Delete the link and the report is gone.

Over 60 KB packed, the inputs are dropped and only the findings travel;
the answer then carries `report_note` saying so.

**Rounds, without storage.** Pass the link you were given back as
`previous_report_link` on the next call. The server unpacks it, compares
problem ids, and the new answer carries:

- `fixed_since_last_check` — ids that are gone
- `still_open` — ids that are still there

That is the whole of the memory: the last answer travels in with the next
question.

---

## Limits

| | |
| --- | --- |
| story | 3,000 characters |
| context | 2,000 characters |
| criteria | 60 |
| test cases | 300 |
| risks | 200 |
| matrix factors | 8, with 8 options each |
| code files | 30, 200 KB each |
| request body | 1 MB |
| time per call | 5 seconds |
| rate | 60 calls a minute per address |

---

## Errors

A tool never answers with a stack trace. Four shapes, all of them a
sentence an agent can act on:

| what happened | what comes back |
| --- | --- |
| wrong shape | `test_cases[2].steps: needs at least one step` |
| too many tests | `Too many tests (412). Send 300 or fewer.` |
| body over 1 MB | `That request is too big (413). Send 1 MB or less.` (HTTP 413) |
| too many calls | `Too many calls (429). …` (HTTP 429) |
| our bug | `Something went wrong on our side (ref 7f3a).` |

The `ref` is in the server log beside the exception. The content that
caused it is not.

---

## Privacy

- **Nothing is stored.** No database, no session, no account. The report
  link holds the report, in the browser.
- **Logs hold counts, never content.** One line per call:
  `mcp tool=review_tests ms=42 criteria=5 tests=14 problems=6 status=ok`.
  No story, no criterion, no test, ever.
- **No API key is involved.** There is no AI behind these tools, so there
  is nothing to authenticate and nothing to bill.
- **Nothing you send is run.** `check_code` reads your files as text.

---

## Turning it on

`/mcp` answers `404` unless it is switched on. The rule:

- **Previews** — on by default.
- **Production** — off, until `QAG_MCP_ENABLED=1` is set in
  Vercel → Settings → Environment Variables (Production), then redeploy.

Setting `QAG_MCP_ENABLED=0` turns it off anywhere.

**Rate limiting.** The 60-a-minute limit in the app is held in one
instance's memory, and a serverless app runs as many instances as it
likes — so it stops one client in a loop, not a crowd. The real guard is a
**Vercel Firewall rate-limit rule on `/mcp`**, which the owner adds in the
dashboard. Checked 2026-11-04: Vercel documents WAF rate limiting as
available on all plans including Hobby, with one free rate-limit rule per
project there.

---

## Checking it works

```
python scripts/mcp_smoke.py                                    # starts the app itself
python scripts/mcp_smoke.py --url https://qa-genius-ashy.vercel.app
```

It acts like a real MCP client — `initialize`, `notifications/initialized`,
`tools/list`, then a whole coupon story through all six tools — and prints
a pass/fail table. CI runs it against a local server on every push.

---

## The tools

<!-- tools:start -->

*This section is generated from the schemas by `python scripts/update_mcp_docs.py`. Do not edit it by hand.*

### `check_story`

Read a user story before anyone writes a test, and say what is wrong with it. Finds words nobody can measure and says what to write instead, warns when the story is really several stories, says when nothing describes what happens if it fails, and lists limits nobody has decided. Use it first, on the story as the team wrote it, before you draft acceptance criteria — fixing a word here is cheaper than rewriting a suite later. Example: send {"story": "As a shopper I want the cart to update quickly so that I can check out"} and it reports that "quickly" is untestable and to say "within 2 seconds" instead.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `story` | `string` | yes | The user story or the bug, in the words the team wrote. (at most 3000 characters) |
| `context` | `string` | no | Anything else that decides the answer: limits, rules, what the feature already does. Limits live here as often as in a criterion. (at most 2000 characters) |
| `story_type` | `user story` \| `bug` \| `feature` | no | What kind of thing this is. It changes nothing in the check. |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

### `review_tests`

Review acceptance criteria and the test cases written for them, the way a senior tester would. Finds tests that expect the opposite of the limit their criterion states, missing tests at the limits and for wrong input, two tests that are the same test, tests whose expected result cannot be judged true or false, and criteria that are too thinly tested. Hands back ready-written tests for the gaps, in the same shape you send tests in. Use it after you have drafted criteria and tests, fix every high problem, and call it again until none come back. Example: send a criterion "orders over $50 ship free" with one test using $60, and it reports that nobody says what happens at exactly $50.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `story` | `string` | yes | The user story or the bug, in the words the team wrote. (at most 3000 characters) |
| `context` | `string` | no | Anything else that decides the answer: limits, rules, what the feature already does. (at most 2000 characters) |
| `criteria` | list of `CriterionIn` | yes | The acceptance criteria, in order. (at most 60) |
| `test_cases` | list of `TestIn` | yes | The tests you wrote for those criteria. (at most 300) |

**`CriterionIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | no | Your id for this criterion. Use the shape "AC-1" and it is kept exactly. Leave it out and ids are given in order: AC-1, AC-2, AC-3. Any other shape is renumbered to AC-1…AC-n by position — the answer says so in notes, and the ids in your test cases' "covers" are renumbered to match. (at most 40 characters) |
| `text` | `string` | yes | The rule in one sentence, with the real numbers in it. "The account locks for 30 minutes after 5 wrong passwords" — not "the account locks quickly". (at most 1000 characters) |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

### `score_risks`

Score a set of risks and say which ones no test reaches. You write the risks and the three scores — how bad, how likely, how hard to notice — and this works out each one's risk score out of 125, its level, and whether a test really covers it (a test that names the risk or does what it describes counts; a test merely claimed does not). It also names the classic failure modes this kind of feature usually has that nobody wrote down, and hands back ready tests for high risks with nothing covering them. Use it after review_tests comes back clean. Example: send a payment story with one risk "the card is charged twice" and no test for it, and it comes back high, "no test", with a question for the product owner.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `story` | `string` | yes | The user story or the bug, in the words the team wrote. (at most 3000 characters) |
| `context` | `string` | no | Anything else that decides the answer: limits, rules. (at most 2000 characters) |
| `criteria` | list of `CriterionIn` | yes | The acceptance criteria, in order. (at most 60) |
| `test_cases` | list of `TestIn` | yes | The tests written for those criteria. (at most 300) |
| `risks` | list of `RiskIn` | yes | The risks you wrote and scored. Write them yourself — this tool checks them, it does not invent them. (at most 200) |

**`CriterionIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | no | Your id for this criterion. Use the shape "AC-1" and it is kept exactly. Leave it out and ids are given in order: AC-1, AC-2, AC-3. Any other shape is renumbered to AC-1…AC-n by position — the answer says so in notes, and the ids in your test cases' "covers" are renumbered to match. (at most 40 characters) |
| `text` | `string` | yes | The rule in one sentence, with the real numbers in it. "The account locks for 30 minutes after 5 wrong passwords" — not "the account locks quickly". (at most 1000 characters) |

**`RiskIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | no | Your id for this risk, such as "R1". (at most 40 characters) |
| `title` | `string` | yes | The failure, in one line. (at most 300 characters) |
| `category` | `string` | no | One of: security, performance, reliability, data, usability, accessibility, functional. Anything else is read as functional. (at most 40 characters) |
| `effect` | `string` | no | What the user suffers when it happens. (at most 600 characters) |
| `cause` | `string` | no | Why it would happen. (at most 600 characters) |
| `how_bad` | `integer` | no | How bad it is if it happens, 1 to 5. 5 is the worst. (1 or more; 5 or less) |
| `how_likely` | `integer` | no | How likely it is to happen, 1 to 5. 5 is near certain. (1 or more; 5 or less) |
| `how_hard_to_notice` | `integer` | no | How hard it would be to notice, 1 to 5. 5 means it could happen and nobody would find out. (1 or more; 5 or less) |
| `linked_criteria` | list of `string` | no | The criterion ids this risk belongs to, such as ["AC-2"]. (at most 60) |
| `tested_by` | list of `string` | no | The test ids you believe already reach this risk. The check reads those tests and will disagree if their words do not match what the risk says goes wrong. (at most 300) |
| `test_idea` | `string` | no | One line saying what a test for this would do. (at most 600 characters) |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |
| `risks` | list of `RiskOut` | no | Every risk, worst first. |
| `untested_high` | list of `string` | no | The ids of high risks no test reaches. Write a test for each or say in writing why not. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`RiskOut`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | The risk's id. |
| `title` | `string` | yes | The failure, in one line. |
| `category` | `string` | yes | What kind of failure it is. |
| `score` | `integer` | yes | How bad × how likely × how hard to notice. Out of 125. |
| `max_score` | `integer` | no | What the score is out of. |
| `level` | `high` \| `medium` \| `low` | yes | high: write a test for it or accept it in writing. medium: worth a test. low: note it and move on. |
| `coverage` | `tested` \| `probably tested` \| `no test` | yes | tested: a test names this risk or does what it describes. "probably tested": a test was claimed but its words do not match what goes wrong. no test: nothing reaches it. |
| `tested_by` | list of `string` | no | The test ids that reach it. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

### `plan_matrix`

Work out the fewest test runs that still put every allowed pair of values together. Send what varies — browser, device, language, role — and the pairs that can never happen, and it returns the runs to do, how many new pairs each one is the first to cover, the pairs your rules forbid, and which runs Playwright cannot drive so somebody has to do them by hand. Use it when you need to decide where to run a suite rather than what to put in it. Example: 4 browsers × 3 devices × 2 sign-in states is 24 combinations, and this returns about 12 runs that still cover every pair.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `factors` | list of `FactorIn` | yes | What varies between runs. At least two. (at most 8; at least 2) |
| `rules` | list of `MatrixRuleIn` | no | Pairs of values that can never happen together. (at most 40) |
| `pinned` | list of object | no | Runs that must be in the plan whatever the arithmetic says, each written {"Browser": "Chrome", "Device": "Phone"}. (at most 40) |

**`FactorIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `name` | `string` | yes | What varies, such as "Browser" or "Device". (at most 40 characters) |
| `options` | list of `string` | yes | Every value it can take, such as ["Chrome", "Firefox", "Safari"]. At least two. (at most 8; at least 2) |

**`MatrixRuleIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `a` | `string` | yes | One side, written "Factor=option", such as "Browser=Firefox". (at most 90 characters) |
| `b` | `string` | yes | The other side, such as "Device=Phone". (at most 90 characters) |
| `reason` | `string` | no | Why they cannot go together, in one line. (at most 300 characters) |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |
| `runs` | list of `RunOut` | no | The runs to do, in order. |
| `combinations` | `integer` | no | How many combinations there are in all. |
| `pairs_possible` | `integer` | no | How many pairs of values are worth covering. |
| `pairs_covered` | `integer` | no | How many of them these runs reach. Always equal to pairs_possible — that is what the plan is for. |
| `impossible_pairs` | list of `string` | no | Pairs your rules forbid, written "Browser=Firefox + Device=Phone". |
| `manual_only` | `integer` | no | How many runs nobody can automate. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`RunOut`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `values` | object | yes | What this run uses, {"Browser": "Chrome", "Device": "Phone"}. |
| `new_pairs` | `integer` | yes | How many pairs of values this run is the first to cover. The numbers add up to pairs_covered. |
| `manual_only` | `boolean` | no | True when Playwright cannot drive this run. |
| `manual_reason` | `string` | no | Why it has to be done by hand. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

### `check_code`

Read automation code and say what a senior tester would send back. Finds tests left with `.only` or `fit` that silently skip the rest of the suite, tests that never actually check anything, fixed sleeps instead of waiting for a state, passwords and tokens written into the source, selectors that will break on the next redesign, and which of your test case ids the code never names. Python is parsed for real; TypeScript and JavaScript get a quick check that brackets and quotes match, which is not a full compile, and the answer says so. Nothing is ever run. Use it after you write or change automation. Example: send one Playwright spec with a leftover `test.only` and it comes back as a high problem on that line.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `framework` | `playwright-ts` \| `playwright-js` \| `playwright-py` \| `cypress` \| `selenium-py` \| `selenium-java` | yes | What the tests are written with. |
| `files` | list of `CodeFileIn` | yes | The files to check. (at most 30; at least 1) |
| `test_cases` | list of `TestIn` | no | The tests this code is supposed to cover. Send them and the answer says which test case ids the code never names. (at most 300) |

**`CodeFileIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `path` | `string` | yes | Where the file lives, such as "tests/checkout.spec.ts". (at most 400 characters) |
| `content` | `string` | yes | The whole file, exactly as it is written. (at most 204800 characters) |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |
| `language` | `string` | no | What these files are written in. |
| `syntax` | object | no | file → what its syntax check actually proved. Python is parsed for real; TypeScript and JavaScript get a quick check that brackets and quotes match, which is not a full compile. |
| `findings` | list of `CodeFindingOut` | no | Everything found, file by file. |
| `traced` | list of `string` | no | Test case ids the code names. |
| `untraced` | list of `string` | no | Test case ids you sent that no file names. |

**`CodeFindingOut`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `file` | `string` | yes | Which file. |
| `line` | `integer` | yes | Which line. 0 when it is about the whole file. |
| `level` | `error` \| `warning` | yes | error: this will not run or will not catch anything. warning: it runs, and it will hurt later. |
| `says` | `string` | yes | What is wrong, in one line. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

### `ship_check`

Decide whether this work is ready to release, and say why. Runs every check at once over the story, criteria, tests and — if you send them — the risks and the test matrix, then gives a decision, a letter grade with the arithmetic behind it, every check with its status, and the list of things to do to reach ready. A check you sent nothing for comes back "not done yet", which never means fine. Use it last, after review_tests comes back with no high problems. Example: send story, criteria and tests with no risks, and the risk check reports "not done yet" and the decision says so.

**Sends**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `previous_report_link` | `string` | no | The report_link this tool gave you last time, if there was one. Send it and the answer says which problems you have fixed since and which are still here. Leave it out on the first call. (at most 200000 characters) |
| `story_label` | `string` | no | The team's own id for this story, such as "AUR-14". It is shown at the top of the report page so a reader can match the report to the ticket. Letters, numbers, - and _ only. (at most 24 characters) |
| `story` | `string` | yes | The user story or the bug, in the words the team wrote. (at most 3000 characters) |
| `context` | `string` | no | Anything else that decides the answer: limits, rules. (at most 2000 characters) |
| `criteria` | list of `CriterionIn` | yes | The acceptance criteria, in order. (at most 60) |
| `test_cases` | list of `TestIn` | yes | The tests written for those criteria. (at most 300) |
| `risks` | list of `RiskIn` | no | The risks, if you scored any. Leave it out and the risk check comes back "not done yet" — never "fine". (at most 200) |
| `matrix_summary` | `MatrixIn` (optional) | no | The test matrix, if you planned one. Leave it out and the matrix check comes back "not done yet". |
| `accepted` | list of `string` | no | Risk ids the team has accepted in writing. An accepted risk is still shown, with its id, but it no longer counts as untested. (at most 200) |

**`CriterionIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | no | Your id for this criterion. Use the shape "AC-1" and it is kept exactly. Leave it out and ids are given in order: AC-1, AC-2, AC-3. Any other shape is renumbered to AC-1…AC-n by position — the answer says so in notes, and the ids in your test cases' "covers" are renumbered to match. (at most 40 characters) |
| `text` | `string` | yes | The rule in one sentence, with the real numbers in it. "The account locks for 30 minutes after 5 wrong passwords" — not "the account locks quickly". (at most 1000 characters) |

**`MatrixIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `runs` | `integer` | no | How many runs are planned. (0 or more) |
| `valid_pairs` | `integer` | no | How many pairs of values are worth covering. (0 or more) |
| `covered_pairs` | `integer` | no | How many of those pairs the runs reach. (0 or more) |
| `manual_only` | `integer` | no | How many runs nobody can automate. (0 or more) |
| `factors` | list of `string` | no | What varies between runs, such as ["browser", "device"]. (at most 40) |

**`RiskIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | no | Your id for this risk, such as "R1". (at most 40 characters) |
| `title` | `string` | yes | The failure, in one line. (at most 300 characters) |
| `category` | `string` | no | One of: security, performance, reliability, data, usability, accessibility, functional. Anything else is read as functional. (at most 40 characters) |
| `effect` | `string` | no | What the user suffers when it happens. (at most 600 characters) |
| `cause` | `string` | no | Why it would happen. (at most 600 characters) |
| `how_bad` | `integer` | no | How bad it is if it happens, 1 to 5. 5 is the worst. (1 or more; 5 or less) |
| `how_likely` | `integer` | no | How likely it is to happen, 1 to 5. 5 is near certain. (1 or more; 5 or less) |
| `how_hard_to_notice` | `integer` | no | How hard it would be to notice, 1 to 5. 5 means it could happen and nobody would find out. (1 or more; 5 or less) |
| `linked_criteria` | list of `string` | no | The criterion ids this risk belongs to, such as ["AC-2"]. (at most 60) |
| `tested_by` | list of `string` | no | The test ids you believe already reach this risk. The check reads those tests and will disagree if their words do not match what the risk says goes wrong. (at most 300) |
| `test_idea` | `string` | no | One line saying what a test for this would do. (at most 600 characters) |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

**Answers**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | The shape of this answer. It changes only when fields do. |
| `tool` | `string` | yes | Which tool answered. |
| `summary` | `string` | yes | One line for a human to read, such as "6 to fix · 5 criteria · 14 tests". Show it; do not parse it. |
| `problems` | list of `Problem` | no | Everything wrong, worst first. Fix every high one and call the tool again. |
| `add_tests` | list of `TestIn` | no | Ready-written tests for gaps nothing covered. They are already in the shape this tool takes back, so you can send them straight in. |
| `ask_the_po` | list of `string` | no | Questions no tool can answer because nobody has decided yet. Show these to the user — do not guess the answers. |
| `notes` | list of `string` | no | Anything else worth knowing that is not a problem. |
| `report_link` | `string` | no | A page showing this answer, for the person you are helping. Everything it needs is after the # — nothing is stored on the server and the server never sees it. Give the user this link. |
| `report_note` | `string` | no | Set only when the answer was too big to pack the inputs into the link, so the page shows the findings without them. |
| `fixed_since_last_check` | list of `string` | no | Problem ids from `previous_report_link` that are gone now. Send the link you were given last time and this fills in. |
| `still_open` | list of `string` | no | Problem ids from `previous_report_link` that are still here. Empty when no previous link was sent. |
| `decision` | `ready` \| `ready with known risks` \| `not ready` | yes | ready: nothing to do. ready with known risks: it can go, and somebody should look at what is listed. not ready: a check failed. |
| `grade` | `GradeOut` (optional) | no | The letter, or null when no check had anything to score. |
| `checks` | list of `CheckOut` | no | Every check, in a fixed order. |
| `path_to_ready` | list of `string` | no | What to do, in order, to turn this into ready. |

**`CheckOut`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Which check this is. |
| `title` | `string` | yes | Its name, for a human. |
| `status` | `pass` \| `warn` \| `fail` \| `accepted` \| `not_checked` | yes | pass: fine. warn: look at it. fail: blocks the release. accepted: signed off in writing. not_checked: you sent nothing for it — this never means fine. |
| `summary` | `string` | yes | What this check found, in one line. |
| `details` | list of `string` | no | The short lines underneath it. |

**`GradeOut`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `letter` | `string` | yes | The grade, such as "B+" or "F". |
| `points` | `integer` | yes | Points scored by the checks that ran. |
| `max` | `integer` | yes | Points those checks were worth. |
| `lines` | list of `string` | no | One line per check, saying what it scored and why. |

**`Problem`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | A stable id for this problem. The same problem keeps the same id between calls, so you can say which one you fixed. |
| `kind` | `limit` \| `gap` \| `copy` \| `weak` \| `depth` \| `clarity` \| `epic` \| `missing` | yes | limit: a number two places disagree about, or nobody decided. gap: something a senior tester always checks that no test does. copy: two tests that are the same test. weak: a test whose expected result cannot be judged true or false. depth: a criterion without enough tests, or without the kinds it needs. clarity: a word nobody can test. epic: the story is really several stories. missing: a criterion with no test at all. |
| `level` | `high` \| `medium` \| `low` | yes | high: fix this before writing more. medium: fix it before release. low: worth a look. |
| `says` | `string` | yes | What is wrong, in one sentence. |
| `fix` | `string` | yes | What to do about it, as an instruction. |
| `criteria` | list of `string` | no | The criterion ids this is about. |
| `tests` | list of `string` | no | The test ids this is about. |

**`TestIn`**

| field | type | required | what it is |
| --- | --- | --- | --- |
| `id` | `string` | yes | Your id for this test, such as "TC-04". (at most 40 characters) |
| `title` | `string` | yes | What this test proves, in one line. (at most 300 characters) |
| `steps` | list of `string` | yes | What the tester does, one action per step. At least one. (at most 50; at least 1) |
| `expected` | `string` | yes | What must be true afterwards, worded so it can only be true or false. "The page shows: Locked for 30 minutes" — not "it works". (at most 1000 characters) |
| `test_data` | `string` | no | The exact values this test uses: the amount, the file size, the number of tries. Say "$50.00", not "an order over the limit". (at most 1000 characters) |
| `covers` | list of `string` | no | The criterion ids this test proves, such as ["AC-1", "AC-3"]. Use the same ids you sent in criteria. A criterion no test names is reported as having no tests. (at most 60) |
| `kind` | `normal` \| `wrong input` \| `at the limit` \| `unusual` | no | What kind of test this is. "normal" is the path that works; "wrong input" is bad data or no permission; "at the limit" uses the exact boundary value; "unusual" is everything rarer. |

<!-- tools:end -->
