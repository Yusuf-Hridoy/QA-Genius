"""Ship check routes. No key, no AI call, nothing stored."""

import html
import json
import re

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.ship_check import CHECK_IDS

client = TestClient(main.app)



REASON = "Behind a feature flag for internal users until the shared counter lands."


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    """Ship check must never reach a model, whatever the body holds."""

    def _never(*args, **kwargs):
        raise AssertionError("Ship check must not call the AI")

    monkeypatch.setattr(llm, "generate_json", _never)


def statuses(body: str) -> dict[str, str]:
    """Every check and what it came back as, in CHECK_IDS order.

    The page shows only the checks that ran, so the statuses are read from
    the report the page carries as data rather than from its layout.
    """
    block = body.split('id="ship-data">', 1)[1].split("</script>", 1)[0]
    data = json.loads(html.unescape(block))
    return {item["id"]: item["status"] for item in data["items"]}


def sample() -> dict:
    with open("qagenius/samples/ship_check.json", encoding="utf-8") as f:
        return json.load(f)


def post(body: dict):
    return client.post("/ship/report", content=json.dumps(body))


# ---------- the page ----------


def test_the_page_loads():
    response = client.get("/ship")
    assert response.status_code == 200
    assert "Make the release call with the reasons attached." in response.text


def test_the_page_says_no_ai_and_no_key():
    body = client.get("/ship").text
    assert "No AI, no key needed." in body


# ---------- an empty run ----------


def test_an_empty_body_leaves_every_check_not_checked():
    response = post({})
    assert response.status_code == 200
    assert set(statuses(response.text).values()) == {"not_checked"}


def test_an_empty_run_ships_with_risks_because_the_core_checks_are_missing():
    body = post({"story": "A story nobody has checked yet."}).text
    assert "Release with known risks" in body
    assert "Not enough to go on" in body
    assert "Criteria with a test, Risks with a test not done yet." in body


def test_no_body_at_all_is_not_an_error():
    assert client.post("/ship/report").status_code == 200


# ---------- the example ----------


def test_the_example_cannot_ship():
    response = client.post("/ship/example")
    assert response.status_code == 200
    assert "Not ready" in response.text
    assert "1 check failed: Risks with a test." in response.text


def test_the_example_has_the_statuses_the_brief_asks_for():
    found = statuses(client.post("/ship/example").text)
    assert found == {
        "clarity": "pass",
        "duel": "warn",
        "coverage": "pass",
        "depth": "warn",
        "risks": "fail",
        "automation": "not_checked",
        "matrix": "not_checked",
    }


def test_the_example_says_five_of_seven_checks_ran():
    assert "5 of 7 checks ran" in client.post("/ship/example").text


def test_the_example_never_names_a_real_company():
    body = client.post("/ship/example").text
    assert "Aurora Storefront" in body


# ---------- a part the browser got wrong ----------


def test_invalid_automation_is_treated_as_missing_and_said_so():
    body = sample()
    body["automation"] = {"script": {"framework": "Playwright"}, "selected_ids": ["TC-001"]}
    response = post(body)
    assert response.status_code == 200
    assert "could not be read, so these were skipped: automation" in response.text
    assert statuses(response.text)["automation"] == "not_checked"


def test_one_bad_part_does_not_hide_the_others():
    body = sample()
    body["automation"] = {"script": "not an automation script"}
    found = statuses(post(body).text)
    assert found["automation"] == "not_checked"
    assert found["clarity"] == "pass"
    assert found["risks"] == "fail"


def test_several_bad_parts_are_all_listed():
    body = sample()
    body["automation"] = {"script": "nope"}
    body["duel_summary"] = {"agreement_pct": "not a number", "forks": "nope"}
    text = post(body).text
    assert "ambiguity duel" in text
    assert "automation" in text


def test_a_body_that_is_not_json_shows_an_error_card():
    response = client.post("/ship/report", content="{not json")
    assert response.status_code == 200
    assert "Could not read your results" in response.text


# ---------- risk acceptance ----------


def test_an_acceptance_turns_the_risk_fail_into_accepted():
    body = sample()
    body["acceptances"] = {"risks": REASON}
    response = post(body)
    assert statuses(response.text)["risks"] == "accepted"
    assert "Release with known risks" in response.text
    assert REASON in response.text


def test_an_acceptance_for_an_unknown_check_is_ignored():
    body = sample()
    body["acceptances"] = {"not_a_check": REASON}
    assert statuses(post(body).text)["risks"] == "fail"


def test_a_short_reason_leaves_the_fail_in_place():
    body = sample()
    body["acceptances"] = {"risks": "ok"}
    assert statuses(post(body).text)["risks"] == "fail"


# ---------- limits ----------


def test_a_body_over_the_limit_is_refused():
    huge = json.dumps({"story": "x" * 2_000_100})
    response = client.post("/ship/report", content=huge)
    assert response.status_code == 413
    assert "too large" in response.text


# ---------- the page's own furniture ----------


def test_the_markdown_block_is_present_and_parses():
    body = client.post("/ship/example").text
    match = re.search(
        r'<script type="application/json" id="ship-md">(.*?)</script>', body, re.DOTALL
    )
    assert match
    markdown = json.loads(match.group(1))
    assert markdown.startswith("# Ship check — Not ready")
    assert "| Risks with a test | ❌ Fail |" in markdown


def test_the_rows_come_in_check_ids_order():
    found = statuses(client.post("/ship/example").text)
    assert tuple(found) == CHECK_IDS


def test_the_page_shows_a_tile_for_every_check_that_ran():
    """Checks that never ran are one muted line, not seven empty tiles."""
    text = client.post("/ship/example").text
    ran = [
        check_id
        for check_id, status in statuses(text).items()
        if status != "not_checked"
    ]
    assert ran
    for check_id in ran:
        assert f'data-check="{check_id}" data-status=' in text
    assert "Not run yet:" in text


def test_accept_with_reason_appears_only_on_a_failed_row():
    body = client.post("/ship/example").text
    rows = body.split('class="card ship-row"')
    accepting = [row for row in rows if "ship-accept" in row]
    assert len(accepting) == 1
    assert 'data-status="fail"' in accepting[0]


def test_each_row_links_to_the_desk_that_fixes_it():
    body = client.post("/ship/example").text
    assert 'href="/risks">Open Risk radar' in body
    assert 'href="/requirements/test-cases">Open Test cases' in body


def test_an_accepted_note_is_escaped_not_run():
    body = sample()
    body["acceptances"] = {"risks": "<script>alert('x')</script> shipping anyway"}
    text = post(body).text
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert" in text


def test_the_verdict_banner_carries_the_tone_of_the_verdict():
    assert "ship-banner ship-bad" in client.post("/ship/example").text

    body = sample()
    body["acceptances"] = {"risks": REASON}
    assert "ship-banner ship-warn" in post(body).text


def test_a_clean_run_gets_the_ok_banner():
    body = sample()
    # Tag the untested high risk, settle the duel and deepen the thin criteria.
    for case in body["test_cases"]["result"]["test_cases"]:
        if case["id"] == "TC-001":
            case["tags"].append("risk:R1")
    body["duel_summary"] = {"agreement_pct": 95, "forks": []}
    body["test_cases"]["criteria"] = body["test_cases"]["criteria"][:2]
    text = post(body).text
    assert "ship-banner ship-ok" in text
    assert "All checks passed." in text


# ---------- criteria without a test case list ----------
# Before step 3 the run has criteria but no suite to carry them, and story
# clarity is judged against them, so they travel on their own.

VAGUE_STORY = {
    "ambiguity_score": 58,
    "clarity_label": "Vague",
    "invest_overall": "Needs work",
    "invest_independent": "Pass",
    "invest_negotiable": "Pass",
    "invest_valuable": "Pass",
    "invest_estimable": "Fail",
    "invest_small": "Pass",
    "invest_testable": "Fail",
    "vague_phrases": [],
    "missing_elements": ["Acceptance criteria (Given/When/Then format)"],
    "suggested_rewrites": ["As a user, I want a persistent left navigation bar."],
    "generated_acceptance_criteria": [],
    "risks": [],
}
NAV_CRITERIA = [
    "The active link is highlighted within 200 ms of the route changing",
    "Below 768 px the bar collapses into a toggle",
    "Every link shows a visible focus ring in tab order",
    "The current page is announced to screen readers",
]


def test_loose_criteria_hold_clarity_at_warn():
    response = client.post(
        "/ship/report", json={"story_analysis": VAGUE_STORY, "criteria": NAV_CRITERIA}
    )
    assert statuses(response.text)["clarity"] == "warn"
    assert "4 acceptance criteria pin it down" in response.text


def test_the_same_story_without_criteria_still_fails():
    response = client.post("/ship/report", json={"story_analysis": VAGUE_STORY})
    assert statuses(response.text)["clarity"] == "fail"
    assert "pin it down" not in response.text


def test_loose_criteria_do_not_make_coverage_look_run():
    """Only clarity reads them; coverage still needs a test case list."""
    response = client.post(
        "/ship/report", json={"story_analysis": VAGUE_STORY, "criteria": NAV_CRITERIA}
    )
    rows = statuses(response.text)
    assert rows["coverage"] == "not_checked"
    assert rows["depth"] == "not_checked"


def test_criteria_that_are_not_a_list_of_text_are_ignored_and_said_so():
    response = client.post(
        "/ship/report", json={"story_analysis": VAGUE_STORY, "criteria": {"a": 1}}
    )
    assert response.status_code == 200
    assert statuses(response.text)["clarity"] == "fail"
    assert "acceptance criteria" in response.text


def test_too_many_criteria_are_ignored_rather_than_an_error():
    response = client.post(
        "/ship/report",
        json={"story_analysis": VAGUE_STORY, "criteria": ["a criterion"] * 41},
    )
    assert response.status_code == 200
    assert statuses(response.text)["clarity"] == "fail"


# ---------- inputs the browser says are out of date ----------
# The status still stands; the reader is told what it was computed from.


def _stale(body: dict, inputs: list[str]) -> str:
    body = dict(body, stale_inputs=inputs)
    return post(body).text


def test_a_stale_input_adds_a_note_under_that_check():
    text = _stale(sample(), ["risks"])
    assert "Built from older work — update Risk radar for an accurate result." in text


def test_the_header_says_the_inputs_are_old():
    # The verdict itself was worked out this minute. Only what it read is
    # older, and the header says so rather than the reason trailing off.
    text = _stale(sample(), ["risks"])
    assert "Worked out just now — some inputs are older" in text
    assert 'class="chip chip-warn ship-stale-header"' in text


def test_nothing_is_said_when_no_input_is_stale():
    text = post(sample()).text
    assert "Built from older work" not in text
    assert "some inputs are older" not in text


def test_an_unknown_id_is_ignored_rather_than_shown():
    text = _stale(sample(), ["nonsense", "../../etc/passwd", "risks"])
    # One note on the page. The report also travels as JSON for the Overview,
    # so the note is counted where a reader would see it.
    assert text.count('class="muted small ship-stale-note"') == 1
    assert "nonsense" not in text


def test_a_body_that_is_not_a_list_is_ignored():
    body = dict(sample(), stale_inputs="risks")
    assert "Built from older work" not in post(body).text


def test_every_check_can_carry_the_note():
    for check, desk in [
        ("coverage", "Test cases"),
        ("depth", "Test cases"),
        ("matrix", "Test matrix"),
        ("automation", "Automation"),
    ]:
        text = _stale(sample(), [check])
        assert f"update {desk} for an accurate result." in text, check


def test_the_note_sits_under_its_own_row():
    text = _stale(sample(), ["risks"])
    start = text.index('data-check="risks"')
    nxt = text.find('data-check="', start + 20)
    row = text[start : nxt if nxt != -1 else len(text)]
    assert "Built from older work" in row


def test_a_confidence_label_never_reaches_a_detail_line() -> None:
    """Ship check and the story page strip it with the same helper."""
    body = sample()
    body["story_analysis"]["missing_elements"] = [
        "No lockout limit [HIGH CONFIDENCE]",
        "The avatar limit is not stated. Confidence: Medium.",
        "The reset link [Confidence: LOW] never expires.",
    ]
    page = post(body).text
    assert "confidence" not in page.lower()
    assert "Missing: No lockout limit" in page
    # The sentence keeps its own full stop and reads as one sentence.
    assert "Missing: The avatar limit is not stated." in page
    assert "Missing: The reset link never expires." in page


def test_the_big_story_warning_is_said_in_plain_words() -> None:
    body = sample()
    body["story"] = (
        "As a registered user, I want to manage my profile, change my password, "
        "set up two-factor authentication with an authenticator app, see and "
        "revoke my active sessions, link my Google or GitHub account, choose "
        "light or dark theme with auto-saving, upload an avatar up to 5 MB, and "
        "permanently delete my account, so that my account is accurate and secure."
    )
    page = post(body).text
    assert "This is too much for one story." in page
    assert "shallow" not in page.lower()
    assert "depth will suffer" not in page.lower()


def test_ship_check_says_when_a_test_disagrees_with_a_limit() -> None:
    """The same note the test-cases desk shows, under How well tested."""
    body = sample()
    suite = body["test_cases"]
    suite["criteria"] = [
        "The user can select a JPEG photo under 2 megabytes and upload it",
        "A photo larger than 2 megabytes is rejected with a message",
    ]
    at_the_limit = dict(suite["result"]["test_cases"][0])
    at_the_limit.update(
        {
            "id": "TC-005",
            "title": "A photo at the size limit",
            "category": "Boundary",
            "steps": ["Choose a 2MB JPEG photo and upload it"],
            "expected_result": "The exact 2MB file is accepted and saved.",
            "test_data": "2MB JPEG",
            "traceability": "AC-1",
        }
    )
    suite["result"]["test_cases"] = [at_the_limit]
    page = post(body).text
    assert "exactly 2 MB should be refused" in page
    assert statuses(page)["depth"] in {"warn", "fail"}
