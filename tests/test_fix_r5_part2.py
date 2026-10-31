"""Fix R5, part two: the smaller things the browser test found.

Each test here failed before its fix. No network, no AI, no key.
"""

import importlib
import json
import re
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius.ship_check import ACCEPT_WORDS, TITLES, compute_ship_report
from qagenius.story_text import strip_markers

client = TestClient(main.app, raise_server_exceptions=False)
ROOT = Path(__file__).resolve().parent.parent
HTML = {"accept": "text/html"}


# ── Task 7 and 13: a new story is an empty page, a saved one comes back ──


def test_a_new_story_clears_every_box_the_last_result_filled():
    """It cleared two of four, so the last story's criteria card stayed up."""
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    for box in ("story-top", "story-output", "story-extra", "duel-output"):
        assert f'id: "{box}"' in flow
    body = flow.split("function clearStoryResults()", 1)[1].split("\n  function ", 1)[0]
    assert "RESULT_BOXES.forEach" in body
    assert "primaryCheckButton()" in body
    assert "delete run.story_view" in body


def test_the_result_card_turns_check_story_into_check_again_and_back():
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    assert '"Check story"' in flow
    assert '"Check again"' in flow
    # Restoring a saved result restores the button it was drawn with.
    restore = flow.split("function restoreStoryPage()", 1)[1].split("\n  /*", 1)[0]
    assert "secondaryCheckButton()" in restore


def test_a_saved_story_restores_every_card_not_just_one():
    """The score card and the criteria drafts arrive by out-of-band swap."""
    body = client.post("/requirements/story/example").text
    assert 'id="story-top"' in body
    assert 'id="story-extra"' in body
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    remember = flow.split("function rememberStoryView()", 1)[1].split("\n  }", 1)[0]
    assert "RESULT_BOXES.forEach" in remember


def test_keeping_the_example_recounts_the_boxes():
    """The counters were drawn before the example filled them: "0 / 3000"."""
    ui = (ROOT / "public" / "stories_ui.js").read_text(encoding="utf-8")
    keep = ui.split("function keepExample", 1)[1].split("\n  function ", 1)[0]
    assert "initFields" in keep


# ── Task 8: the Story ID is saved only when it is one ────────────────────


def test_the_story_id_field_is_empty_with_a_faded_hint():
    body = client.get("/requirements/story").text
    assert 'placeholder="e.g. CART-204"' in body
    assert "Leave it empty and we&#39;ll number it." in body
    # No silent cut at 24: a long id is refused with a message instead.
    field = body.split('id="story-label"', 1)[1].split(">", 1)[0]
    assert "maxlength" not in field


def test_a_placeholder_never_looks_like_something_that_was_typed():
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    block = css.split("::placeholder,input::placeholder,textarea::placeholder{", 1)[1]
    block = block.split("}", 1)[0]
    assert "font-style:italic" in block
    assert "var(--muted)" in block


def test_a_half_typed_id_is_never_saved():
    """Typing AUTH-100 passes through AUTH-10, which used to be stored."""
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    typing = flow.split('if (closest(event.target, "#story-label")) {', 1)[1]
    typing = typing.split("}", 1)[0]
    assert "checkStoryLabel()" in typing
    assert "saveStoryLabel()" not in typing
    # It is written when the field is left, not while it is being filled.
    assert 'if (closest(event.target, "#story-label")) saveStoryLabel();' in flow


def test_an_id_over_twenty_four_characters_is_refused_not_cut():
    flow = (ROOT / "public" / "requirements_flow.js").read_text(encoding="utf-8")
    assert 'var LABEL_TOO_LONG = "That is too long. Use 24 characters or fewer."' in flow
    assert "if (wanted.length > LABEL_MAX) return LABEL_TOO_LONG;" in flow


# ── Task 10: Ship check keeps the accepted risk's details ────────────────


LONG = "Behind a flag for internal users until the shared counter lands."


def _ship_body(acceptances: dict) -> dict:
    return {
        "story": "As a shopper, I want my Aurora Storefront cart saved.",
        "risk_analysis": {
            "analysis": {
                "failure_modes": [
                    {
                        "id": "R-01",
                        "title": "The saved cart is lost",
                        "category": "Data",
                        "cause": "The cart is not written",
                        "effect": "The shopper starts again",
                        "severity": 5,
                        "likelihood": 5,
                        "detectability": 5,
                        "severity_reason": "",
                        "likelihood_reason": "",
                        "detectability_reason": "",
                        "test_idea": "",
                        "related_criteria": [],
                        "covered_by": [],
                    }
                ],
                "summary": "",
            },
            "cases": [],
            "criteria": [],
        },
        "risk_acceptances": acceptances,
    }


def _ship_items(body: dict) -> dict:
    import html as html_mod

    text = client.post("/ship/report", json=body).text
    block = text.split('id="ship-data">', 1)[1].split("</script>", 1)[0]
    data = json.loads(html_mod.unescape(block))
    return {item["id"]: item for item in data["items"]}, text


def test_an_accepted_risk_keeps_its_owner_and_review_date_on_the_page():
    body = _ship_body(
        {"R-01": {"reason": LONG, "owner": "Web team", "review_date": "2099-11-12"}}
    )
    items, text = _ship_items(body)
    assert items["risks"]["status"] == "accepted"
    note = items["risks"]["accepted_note"]
    assert LONG in note
    assert "Owner: Web team" in note
    assert "Review by 2099-11-12" in note
    assert "Web team" in text


def test_an_overdue_acceptance_says_the_review_date_passed_and_asks_for_a_look():
    body = _ship_body(
        {"R-01": {"reason": LONG, "owner": "Web team", "review_date": "2020-01-01"}}
    )
    items, text = _ship_items(body)
    assert items["risks"]["status"] == "warn"
    assert items["risks"]["review_passed"] is True
    assert "Review date passed" in items["risks"]["accepted_note"]
    assert "Web team" in items["risks"]["accepted_note"]
    assert "Review date passed" in text


def test_the_markdown_carries_the_story_the_grade_and_every_acceptance():
    body = _ship_body(
        {"R-01": {"reason": LONG, "owner": "Web team", "review_date": "2099-11-12"}}
    )
    body["story_label"] = "CART-204"
    body["story_status"] = "review"
    text = client.post("/ship/report", json=body).text
    markdown = json.loads(text.split('id="ship-md">', 1)[1].split("</script>", 1)[0])
    assert "**Story ID:** CART-204" in markdown
    assert "Ready for review" in markdown
    assert "**Grade:**" in markdown
    assert LONG in markdown
    assert "Owner: Web team" in markdown
    assert "2099-11-12" in markdown


# ── Task 14: small correctness items ─────────────────────────────────────


def test_how_well_tested_does_not_ask_you_to_accept_a_risk():
    assert ACCEPT_WORDS["depth"] == "Accept anyway and say why"
    assert ACCEPT_WORDS["matrix"] == "Accept anyway and say why"
    assert ACCEPT_WORDS["risks"] == "Accept this risk and say why"
    assert TITLES["depth"] == "How well tested"
    template = (
        ROOT / "qagenius" / "templates" / "_ship_check_result.html"
    ).read_text(encoding="utf-8")
    assert "accept_words.get(item.id" in template


def test_the_high_risk_row_lists_only_high_risks():
    from qagenius.models import RiskAnalysis
    from qagenius.ship_check import ShipInputs
    from tests.test_ship_check import failure_mode

    inputs = ShipInputs(
        story="As a shopper, I want my account locked.",
        criteria=["The account locks after 5 wrong passwords"],
        risk_analysis=RiskAnalysis(
            failure_modes=[
                failure_mode("R1", 5, 4).model_copy(update={"title": "A high one"}),
                failure_mode("R2", 3, 2).model_copy(update={"title": "A medium one"}),
            ]
        ),
        today=date(2026, 1, 1),
    )
    item = next(
        one for one in compute_ship_report(inputs).items if one.id == "risks"
    )
    assert all(line.startswith("High ·") for line in item.details)
    assert item.secondary == ["Medium · R2 A medium one — no test"]


def test_the_example_never_says_nothing_to_add_beside_its_own_complaints():
    body = client.post("/requirements/test-cases/example").text
    if "Nothing to add" in body:
        assert "note on weak cases" not in body
        assert "notes on weak cases" not in body
        assert "still need more tests" not in body


def test_verify_and_its_cousins_never_reach_a_criterion():
    assert strip_markers("The lock lasts 30 minutes [VERIFY].") == (
        "The lock lasts 30 minutes."
    )
    assert strip_markers("A rule [NOT PROVIDED] and another [PLEASE CONFIRM]") == (
        "A rule and another"
    )
    assert strip_markers("Lock after 5 tries [TBD]") == "Lock after 5 tries"
    web = (ROOT / "qagenius" / "web.py").read_text(encoding="utf-8")
    assert "strip_markers(one) for one in result.generated_acceptance_criteria" in web


def test_the_example_lockout_is_the_same_length_everywhere():
    """One sample said 15 minutes while every other one said 30."""
    for name in ("duel.json", "story_check.json", "risk_radar.json", "ship_check.json"):
        text = (ROOT / "qagenius" / "samples" / name).read_text(encoding="utf-8")
        assert "15 minutes" not in text, name
        assert "15-minute" not in text, name


def test_the_delete_all_banner_says_so_and_offers_one_button():
    ui = (ROOT / "public" / "stories_ui.js").read_text(encoding="utf-8")
    assert 'var ALL_GONE_WORDS = "All stories deleted. Start a new one.";' in ui
    # It is said where it happened, not again on every page load.
    start = ui.split("function start()", 1)[1].split("\n  global.QAGStoriesUI", 1)[0]
    assert "storyWasDeleted()) deletedBar()" not in start


def test_freshness_says_which_thing_changed():
    run_state = (ROOT / "public" / "run_state.js").read_text(encoding="utf-8")
    assert 'story: "Your story changed after this was built"' in run_state
    assert 'criteria: "Your criteria changed"' in run_state
    assert "Your story was edited" not in run_state.split("PART_WORDS = {", 1)[1]


# ── Task 12: unknown pages, favicon, robots ──────────────────────────────


def test_an_unknown_path_is_a_friendly_404_not_a_500():
    response = client.get("/no-such-desk", headers=HTML)
    assert response.status_code == 404
    assert "This page doesn't exist." in response.text
    assert "Go to Overview" in response.text
    # Still the app, not a bare browser page.
    assert "QA-Genius" in response.text


def test_a_fetch_for_an_unknown_path_gets_json_not_a_page():
    response = client.get("/no-such-desk")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_the_flow_root_goes_to_the_story_step():
    response = client.get("/requirements", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/requirements/story"


def test_the_tab_icon_and_robots_are_served():
    icon = client.get("/favicon.ico")
    assert icon.status_code == 200
    assert icon.content[:4] == b"\x00\x00\x01\x00"
    svg = client.get("/favicon.svg")
    assert svg.status_code == 200
    assert "<svg" in svg.text
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert robots.text.startswith("User-agent: *")
    assert '<link rel="icon" href="/favicon.svg"' in client.get("/").text


# ── Task 15: security basics ─────────────────────────────────────────────


def test_every_response_carries_the_security_headers():
    for path in ("/", "/requirements/story", "/ship", "/no-such-desk"):
        headers = client.get(path, headers=HTML).headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        policy = headers["Permissions-Policy"]
        for feature in ("camera=()", "microphone=()", "geolocation=()"):
            assert feature in policy
        csp = headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "https://fonts.gstatic.com" in csp
        assert "https://fonts.googleapis.com" in csp
        assert "'unsafe-inline'" not in csp.split("script-src", 1)[1]


def test_the_one_inline_script_carries_that_response_s_nonce():
    body = client.get("/").text
    nonce = re.search(r'<script nonce="([^"]+)">', body)
    assert nonce, "the theme script has no nonce"
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "'nonce-" in csp
    # A fresh nonce per response: a fixed one is no nonce at all.
    again = re.search(r'<script nonce="([^"]+)">', client.get("/").text)
    assert again.group(1) != nonce.group(1)


def test_the_api_docs_and_the_dev_pages_are_gone_without_the_flag(monkeypatch):
    monkeypatch.delenv("QAG_DEV", raising=False)
    import qagenius.web

    production = importlib.reload(qagenius.web)
    try:
        shut = TestClient(production.app, raise_server_exceptions=False)
        for path in ("/docs", "/redoc", "/openapi.json", "/dev/rings", "/dev/next-row"):
            assert shut.get(path).status_code == 404, path
    finally:
        monkeypatch.setenv("QAG_DEV", "1")
        importlib.reload(qagenius.web)
        importlib.reload(main)


def test_the_key_box_is_hidden_while_it_is_pasted():
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    assert ".masked{-webkit-text-security:disc}" in css
    # `text-security` without the prefix is not a property any browser has.
    assert ";text-security:disc" not in css
    app_js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    assert 'window.CSS.supports("-webkit-text-security", "disc")' in app_js
    fallback = app_js.split("function maskKeyBox", 1)[1].split("\n  }", 1)[0]
    assert 'box.type = hidden ? "password" : "text"' in fallback
    assert "Show" in app_js
