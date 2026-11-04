# Changelog

What changed, and why it mattered. Newest first.

## 2.1.0

**QA-Genius for AI agents.** A second door: an MCP server at `/mcp`, so
Claude can call the same checks the website runs. Claude writes the
criteria, tests, risks and code; QA-Genius checks them with plain Python.
No AI call, no API key, nothing stored.

### Added

- **Six MCP tools** — `check_story`, `review_tests`, `score_risks`,
  `plan_matrix`, `check_code`, `ship_check`. All read-only, all
  deterministic, all answering in one shape.
- **A service layer** (`qagenius/services/`) that the website and the MCP
  door both call, so the two can never disagree about the same story.
- **Report links.** Every answer carries a link to a `/report` page that
  shows the whole report. The data sits after the `#`, which a browser
  never sends, so the server has not seen it and has nothing to store.
- **Rounds without storage.** Send back the previous `report_link` and the
  answer says which problems are `fixed_since_last_check` and which are
  `still_open`.
- **A `/report` page** in the site's own design, with the decision, the
  stat row, every problem fixed or still open, the PO's questions, and a
  button that opens the whole thing as a new saved story in the desks.
- **A Claude skill** in `integrations/claude/qa-genius/`.
- **`scripts/mcp_smoke.py`** — acts like a real MCP client over HTTP and
  walks a whole story through all six tools. CI runs it on every push.
- **CI** (`.github/workflows/ci.yml`) — ruff, pytest, the JavaScript
  tests, the smoke test, and a check that the app still imports with only
  the runtime dependencies installed.
- **`docs/mcp.md`**, with the tool reference generated from the schemas so
  it cannot drift.

### Fixed

- **Numbers inside a quoted message are no longer read as a test's
  value.** A test with a $40 cart expecting *"Refused with 'This coupon
  needs an order of at least $50.'"* was reported as having decided what
  happens at exactly $50. It had decided nothing — the $50 was the
  product's own error message. Quoted text in steps and expected results
  is now ignored when reading what a test is testing, and the order of
  trust is test data, then steps, then title. **This fixes the website
  too**: both doors run the same engine.
- **Two tests that do the same thing with the same data are now flagged as
  copies**, even when the titles were reworded enough to pass the name
  check. Renaming the copy was the commonest way a duplicate survived
  review.

### Changed

- `/mcp` is off in production until `QAG_MCP_ENABLED=1` is set, and on by
  default in previews.
- `RiskIn` fields are now `how_bad`, `how_likely` and `how_hard_to_notice`
  — plain words for the three FMEA scores.

## 2.0.0

The v2 rebuild: FastAPI, Jinja2 and HTMX, with the senior-tester rules
running in plain Python beside every AI call.
