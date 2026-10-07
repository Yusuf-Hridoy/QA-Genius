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

## Troubleshooting
- `python scripts/check_key.py` checks one provider key with a tiny JSON
  request. It asks for the provider id and the key (hidden while typing)
  and prints `OK <provider> <model>` or the cleaned error. The key is
  never printed.
