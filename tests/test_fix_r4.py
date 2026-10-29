"""The screens a real browser test found unclear, pinned down.

Each test here names the thing a reader saw and what they must see instead:
a Ship check whose main button went to the wrong desk, a letter grade with
no arithmetic beside it, a bracket count calling itself a compiler, and a
two-reader table written in snake_case.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius.models import RiskAnalysis
from qagenius.ship_check import ACCEPTABLE, CHECK_IDS, TITLES
from qagenius.ship_grade import grade_for
from qagenius.web import plain_name
from tests.factories import suite
from tests.test_ship_check import HIGH, failure_mode, report

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(main.app, raise_server_exceptions=False)


# ── Ship check: the main button, the grade, and who may accept ──────────────


def _ship(**body) -> str:
    return client.post("/ship/report", json=body).text


def _todo_order(markup: str) -> list[str]:
    return re.findall(r'class="card ship-row todo-row" data-check="([a-z_]+)"', markup)


def test_the_main_button_opens_the_first_check_that_needs_fixing() -> None:
    """It used to follow the order the checks are computed in, so a story
    that only needed a look sent the reader to the Story desk while a real
    failure sat under it."""
    body = _ship(
        story="As a shopper, I want my cart kept so I can finish later.",
        criteria=["Given a cart When I close the tab Then it is still there"],
        story_analysis={
            "ambiguity_score": 40,
            "vague_phrases": [],
            "invest_assessment": {},
            "missing_criteria": [],
        },
        risk_analysis={
            "analysis": RiskAnalysis(failure_modes=[HIGH]).model_dump()
        },
    )
    order = _todo_order(body)
    assert order, body[:400]
    # The failing check is first, whatever order the checks were computed in.
    assert order[0] == "risks"
    assert "Open Risk radar →" in body
    main_button = re.search(
        r'<a class="btn btn-primary" href="([^"]+)">Open ([^<]+)</a>', body
    )
    assert main_button, "no main button on the ship report"
    assert main_button.group(1) == "/risks"


def test_what_to_do_next_puts_needs_fixing_above_check_this() -> None:
    body = client.post("/ship/example").text
    order = _todo_order(body)
    statuses = re.findall(r'todo-row" data-check="[a-z_]+" data-status="(\w+)"', body)
    assert statuses, body[:400]
    # Every fail comes before every warn.
    assert statuses == sorted(statuses, key=lambda one: 0 if one == "fail" else 1)
    assert order[0] == "risks"


def test_the_grade_says_why_on_the_page() -> None:
    """A letter on its own is a letter nobody can argue with."""
    body = client.post("/ship/example").text
    assert 'id="grade-reason"' in body
    assert "See how it's worked out" in body
    reason = re.search(r'<p class="grade-reason" id="grade-reason">([^<]+)</p>', body)
    assert reason, body[:400]
    assert re.match(r"^[A-F][+-]? — \d+ of \d+ points\.", reason.group(1).strip())


def test_a_capped_grade_says_it_was_capped_and_why() -> None:
    result = report(
        story="As a shopper, I want my cart kept so I can finish later.",
        criteria=["Given a cart When I close the tab Then it is still there"],
        test_cases=suite(),
        risk_analysis=RiskAnalysis(failure_modes=[HIGH, failure_mode("R2", 5, 4)]),
    )
    grade = grade_for(result)
    assert grade is not None
    if grade.capped:
        assert "Capped at D or below because the decision is Not ready." in grade.reason
    assert grade.reason.startswith(grade.letter)


def test_accepting_a_risk_is_offered_only_where_it_means_something() -> None:
    """A criterion with no test is fixed, not signed off."""
    assert set(ACCEPTABLE) == {"risks", "depth", "matrix"}
    for check_id in ("clarity", "coverage", "duel"):
        assert check_id not in ACCEPTABLE
    body = client.post("/ship/example").text
    offered = set(re.findall(r'class="btn btn-sm ship-accept" data-check="(\w+)"', body))
    assert offered <= set(ACCEPTABLE), offered


def test_the_risks_row_is_named_for_what_it_counts() -> None:
    """"Risks with a test" read as the opposite of what the row says."""
    assert TITLES["risks"] == "High risks without a test"
    assert "risks" in CHECK_IDS


def test_the_ship_report_names_the_story_it_is_about() -> None:
    body = _ship(
        story="As a shopper, I want my cart kept so I can finish later.",
        story_label="CART-204",
        story_status="review",
        criteria=["Given a cart When I close the tab Then it is still there"],
    )
    assert '<span class="chip chip-id">CART-204</span>' in body
    assert "Ready for review" in body
    markdown = json.loads(
        re.search(r'<script type="application/json" id="ship-md">(.*?)</script>', body, re.S).group(1)
    )
    assert markdown.splitlines()[1] == "**Story ID:** CART-204 · Ready for review"


def test_a_story_id_that_is_not_one_never_reaches_the_report() -> None:
    body = _ship(
        story="As a shopper, I want my cart kept so I can finish later.",
        story_label="not a valid id at all",
        criteria=["Given a cart When I close the tab Then it is still there"],
    )
    assert "not a valid id at all" not in body


# ── honest words ────────────────────────────────────────────────────────────


def test_a_bracket_count_never_calls_itself_a_compiler() -> None:
    body = client.post("/requirements/automation/example").text
    assert "Quick check: brackets and quotes match (not a full compile)." in body
    assert "all fine" not in body
    assert "no syntax errors" not in body


def test_python_keeps_the_claim_it_can_make() -> None:
    from qagenius.models import AutomationScript
    from qagenius.web import _syntax_label

    python = AutomationScript(
        framework="Playwright · Python",
        project_structure=[],
        test_file_name="test_cart.py",
        test_code="def test_cart():\n    assert True\n",
        setup_instructions=[],
        execution_command="pytest",
    )
    typescript = python.model_copy(update={"framework": "Playwright · TypeScript"})
    assert _syntax_label(python, []) == "parsed"
    assert _syntax_label(typescript, []) == "brackets match"
    assert _syntax_label(typescript, ["one"]) == "1 error"


def test_the_two_readers_name_things_the_way_a_person_would() -> None:
    assert plain_name("coupon_processing_speed") == "Coupon processing speed"
    assert plain_name("max-upload-size") == "Max upload size"
    assert plain_name("") == ""
    # A product name keeps its own case: only the first word is touched.
    assert plain_name("items_in_MyCart") == "Items in MyCart"
    duel = (ROOT / "qagenius" / "templates" / "_duel_result.html").read_text(
        encoding="utf-8"
    )
    for field in ("r.topic", "n.name", "m.name", "fork.topic"):
        assert f"{{{{ {field} | plain_name }}}}" in duel, field


def test_the_senior_tester_does_not_say_nothing_to_add_over_a_thin_suite() -> None:
    from qagenius.web import _nothing_to_add_line

    from qagenius.shadow_qa.review import CaseReview

    empty = CaseReview(added=[], more=[], covered=["a", "b"], conflicts=[], quality=[])
    assert "Nothing to add." in _nothing_to_add_line(empty)
    thin = _nothing_to_add_line(empty, thin=4, total=5)
    assert thin == (
        "No extra tests to add — but 4 of 5 criteria still need more tests "
        "(see below)."
    )
    assert "Nothing to add" not in thin


# ── the matrix keeps the reasons it was given ───────────────────────────────


def test_the_reasons_under_each_factor_survive_a_rebuild() -> None:
    payload = {
        "factors": [
            {"name": "Browser", "values": ["chromium", "firefox"]},
            {"name": "Device", "values": ["desktop", "phone"]},
        ],
        "rules": [],
        "pinned": [],
        "reasons": {"browser": "Your shoppers use both."},
    }
    body = client.post("/requirements/matrix/build", json=payload).text
    data = json.loads(
        re.search(r'id="matrix-data">(.*?)</script>', body, re.S).group(1)
    )
    assert data["reasons"] == {"browser": "Your shoppers use both."}


def test_a_saved_matrix_brings_its_reasons_back_with_it() -> None:
    saved = {
        "factors": [
            {"name": "Browser", "values": ["chromium", "firefox"]},
            {"name": "Device", "values": ["desktop", "phone"]},
        ],
        "rules": [],
        "pinned": [],
        "reasons": {"browser": "Your shoppers use both."},
        "from_ai": True,
    }
    body = client.post(
        "/requirements/matrix/suggest",
        data={"user_story": "A story.", "saved_json": json.dumps(saved)},
    ).text
    assert "Your shoppers use both." in body


# ── the Story desk's own fields and buttons ────────────────────────────────


def test_the_story_id_rule_sits_beside_the_field() -> None:
    """A bad id used to be fixed silently, or dropped without a word."""
    body = client.get("/requirements/story").text
    assert 'id="story-label-help">Use letters, numbers, - or _ (max 24).' in body
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    # And the same sentence lives in one place in each file that says it.
    assert 'var LABEL_RULE = "Use letters, numbers, - or _ (max 24).";' in flow
    store = (ROOT / "public" / "story_store.js").read_text(encoding="utf-8")
    assert 'var LABEL_RULE = "Use letters, numbers, - or _ (max 24).";' in store


def test_the_story_form_keeps_one_main_button_and_hides_the_rest() -> None:
    """Five buttons in a row wrapped onto two lines at 1440px."""
    body = client.get("/requirements/story").text
    actions = body.split('<div class="form-actions">')[1].split("</div>")[0]
    assert actions.count("btn-primary") == 1
    assert 'id="story-more"' in body
    assert 'id="story-more-list"' in body
    # Load example moved under More rather than beside the main button.
    more = body.split('id="story-more-list" hidden>')[1].split("</div>")[0]
    assert 'id="load-example"' in more


def test_the_story_box_is_not_refilled_by_the_browser() -> None:
    """Starting a new story reloads the same URL, and Chrome put the old
    story's words back into the box after the page had emptied it."""
    body = client.get("/requirements/story").text
    assert '<form id="story-form" autocomplete="off"' in body


def test_a_pop_up_save_is_the_main_button_while_the_pop_up_is_open() -> None:
    story = client.get("/requirements/story").text
    assert 'class="btn btn-sm btn-pop-save" id="draft-save"' in story
    ship = client.post("/ship/example").text
    assert "btn-pop-save ship-accept-save" in ship
    risks = client.post("/risks/example").text
    assert "btn-pop-save risk-accept-save" in risks


def test_the_scores_a_reader_changed_are_called_theirs() -> None:
    """"Typical scores for this kind of problem" under a number somebody
    typed themselves is the page arguing with them."""
    sample = json.loads(
        re.search(
            r'id="risk-data">(.*?)</script>', client.post("/risks/example").text, re.S
        ).group(1)
    )
    body = client.post(
        "/risks/rescore?by=scores",
        json={
            "analysis": sample["analysis"],
            "cases": sample["cases"],
            "criteria": sample["criteria"],
        },
    ).text
    # The JSON block carries the data the page was built from; what the
    # reader sees is everything outside it.
    shown = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    assert "Your scores" in shown
    assert "Typical scores for this kind of problem." not in shown
    assert "These scores are the AI's guess" not in shown
    # The automatic recheck has changed nothing, so it says nothing new.
    by_code = client.post(
        "/risks/rescore?by=code",
        json={
            "analysis": sample["analysis"],
            "cases": sample["cases"],
            "criteria": sample["criteria"],
        },
    ).text
    assert "Why these scores" in re.sub(r"<script.*?</script>", "", by_code, flags=re.S)
