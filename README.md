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

## Troubleshooting
- `python scripts/check_key.py` checks one provider key with a tiny JSON
  request. It asks for the provider id and the key (hidden while typing)
  and prints `OK <provider> <model>` or the cleaned error. The key is
  never printed.
