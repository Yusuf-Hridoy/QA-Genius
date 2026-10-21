"""The small things a full test run turned up. One file, one issue each."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "qagenius" / "samples"
APP_JS = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "public" / "style.css").read_text(encoding="utf-8")


def _sample(name: str) -> dict:
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


# ── 18: the three samples are one run ───────────────────────────────────────


def test_the_three_samples_use_the_same_criteria():
    # A reader who loads all three examples must not meet three different
    # lockout rules for one story.
    story = _sample("story_check")["result"]["generated_acceptance_criteria"]
    cases = _sample("test_cases")["criteria"]
    risks = _sample("risk_radar")["criteria"]
    assert story == cases == risks
    assert len(story) == 5


def test_the_samples_agree_about_the_numbers():
    whole = "\n".join(_sample("story_check")["result"]["generated_acceptance_criteria"])
    assert "5 times within 10 minutes" in whole
    assert "30 minute" in whole
    # Nothing left over from the older draft.
    assert "15 minutes" not in whole
    assert "60 seconds" not in whole


# ── 20: one long line of code never scrolls the page sideways ──────────────


def test_the_code_column_may_shrink_and_the_code_scrolls_inside_it():
    assert ".file-code{min-width:0}" in CSS
    assert "overflow-x:auto" in CSS.split(".file-code pre.code{", 1)[1][:120]


# ── 21: the slow desks say how long they take ───────────────────────────────


def test_the_busy_line_can_appear_without_a_card_or_a_button():
    busy = (ROOT / "public" / "busy.js").read_text(encoding="utf-8")
    # Automation builds its form with no card around the buttons.
    assert 'button.closest("form")' in busy
    # The matrix asks the model the moment the page opens, with no press.
    assert "noteUnder" in busy
    matrix = (ROOT / "public" / "test_matrix.js").read_text(encoding="utf-8")
    assert "QAGBusy.noteUnder" in matrix


def test_the_two_reader_button_says_it_is_reading():
    body = client.get("/requirements/story").text
    assert 'data-busy-label="Reading…"' in body
    assert '<span class="btn-label">Run the two-reader check</span>' in body


# ── 22: one primary on a stale page ─────────────────────────────────────────


def test_the_matrix_button_steps_back_while_the_card_offers_the_same_action():
    assert 'body[data-card-primary="matrix"] #matrix-suggest.btn-primary' in CSS


# ── 23: the key panel is reachable from a keyboard ──────────────────────────


def test_opening_the_key_panel_moves_focus_into_it():
    block = APP_JS.split("function openDrawer(", 1)[1].split("\n  }", 1)[0]
    assert 'document.getElementById(focusAdd ? "drawer-key" : "drawer-provider")' in block
    assert "into.focus()" in block


def test_closing_it_gives_the_focus_back():
    block = APP_JS.split("function closeDrawer(", 1)[1].split("\n  }", 1)[0]
    assert 'document.getElementById("key-chip")' in block


# ── 25: nothing private on a wire that does not need it ─────────────────────


EXAMPLES = [
    "/requirements/story/example",
    "/requirements/test-cases/example",
    "/requirements/test-cases/example-strengthen",
    "/requirements/automation/example",
    "/bugs/example",
    "/insights/example",
    "/insights/example-explained",
    "/risks/example",
    "/ship/example",
    "/requirements/matrix/example",
]


def test_an_example_is_asked_for_with_post():
    # A GET lands in browser history and in a server log. Nothing a reader
    # typed is ever in one of these URLs, and now nothing can be.
    for path in EXAMPLES:
        assert client.post(path).status_code == 200, path
        assert client.get(path).status_code in (404, 405), path


def test_the_keys_header_goes_only_to_the_calls_that_use_it():
    block = APP_JS.split("var AI_PATHS = [", 1)[1].split("];", 1)[0]
    for path in EXAMPLES:
        assert path not in block, path
    for path in ("/requirements/story/run", "/risks/run", "/bugs/run"):
        assert path in block, path
    # And the handler really drops it for everything else.
    handler = APP_JS.split('addEventListener("htmx:configRequest"', 1)[1]
    assert 'delete detail.headers["X-QAG-Keys"]' in handler


# ── 26: a paste that does not fit says so ───────────────────────────────────


def test_a_cut_paste_is_not_silent():
    assert "Only the first " in APP_JS
    assert "characters were kept." in APP_JS
    block = APP_JS.split("function pasteWouldBeCut(", 1)[1].split("\n  }", 1)[0]
    assert "box.maxLength" in block
    assert "selectionEnd" in block


# ── found in review: an invalid escape ──────────────────────────────────────


def test_the_heat_sheet_header_is_a_valid_string():
    source = (ROOT / "qagenius" / "risk_register_exports.py").read_text(
        encoding="utf-8"
    )
    assert "Severity / Likelihood" in source
    assert "Severity \\ Likelihood" not in source


# ── 19: a check with no problems reads as fine ──────────────────────────────


def test_how_well_tested_reads_fine_when_nothing_is_wrong():
    # A run showed "check this" over a suite with nothing wrong in it: the
    # conflict notes under it were read off numbers in the test titles.
    from qagenius.models import RiskAnalysis
    from qagenius.ship_check import ShipInputs, compute_ship_report
    from tests.factories import case, suite

    criteria = ["The account locks after 5 failed attempts within 10 minutes"]
    cases = suite(
        case(
            case_id="TC-001",
            title="Account locks after 5 failed attempts",
            traceability="AC-1",
            steps=["Enter a wrong password 5 times"],
            test_data="attempts=5",
            expected_result="The account is locked and sign-in is refused",
        ),
        case(
            case_id="TC-002",
            category="Boundary",
            title="Four failures do not lock the account",
            traceability="AC-1",
            steps=["Enter a wrong password 4 times", "Enter the correct one"],
            test_data="attempts=4",
            expected_result="The shopper is signed in and nothing is locked",
        ),
    )
    report = compute_ship_report(
        ShipInputs(
            criteria=criteria,
            test_cases=cases,
            risk_analysis=RiskAnalysis(failure_modes=[]),
        )
    )
    depth = next(item for item in report.items if item.id == "depth")
    assert depth.details == []
    assert depth.status in ("pass", "warn")
    assert not any("exactly" in line for line in depth.details)
