"""Fix R5: what a round-two browser test found, pinned down.

Every test here failed before its fix. The LLM is faked throughout; no
network, no key, no real provider.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.web import AI_ERROR_HEADER, ai_error_words

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent

KEYS_HEADER = {
    "X-QAG-Keys": json.dumps(
        [
            {"provider": "gemini", "key": "first"},
            {"provider": "groq", "key": "second"},
        ]
    )
}

STORY = "As a shopper, I want my account to lock quickly."
CRITERIA = json.dumps(["The account locks after 5 failed attempts"])

DESKS = [
    ("/requirements/story/run", {"user_story": STORY}, "Could not check the story"),
    (
        "/requirements/story/duel",
        {"user_story": STORY},
        "Could not run the two-reader check",
    ),
    (
        "/requirements/test-cases/run",
        {"user_story": STORY, "criteria_json": CRITERIA},
        "Could not write test cases",
    ),
    ("/risks/run", {"user_story": STORY}, "Could not find risks"),
]


# ── Task 3: an AI failure always says something, in plain words ──────────


def _raising(monkeypatch, error: Exception) -> None:
    def fake(*args, **kwargs):
        raise error

    monkeypatch.setattr(llm, "generate_json", fake)


@pytest.mark.parametrize("path,form,title", DESKS)
def test_a_refused_key_names_the_provider_and_no_code(monkeypatch, path, form, title):
    """"…failed (400): Error code: 400" is not a sentence anybody can act on."""
    _raising(monkeypatch, llm.InvalidKeyError([], provider="Gemini"))
    response = client.post(path, data=form, headers=KEYS_HEADER)
    body = response.text
    assert f"<h2>{title}</h2>" in body
    assert "Your Gemini key was refused. Check it in Keys, or try your other key." in body
    assert "400" not in body
    assert "Error code" not in body


@pytest.mark.parametrize("path,form,title", DESKS)
def test_every_ai_failure_carries_the_header_that_keeps_it_out_of_the_result(
    monkeypatch, path, form, title
):
    """The browser needs to know this is a failure before it swaps it in."""
    _raising(monkeypatch, llm.AllKeysBusyError([]))
    response = client.post(path, data=form, headers=KEYS_HEADER)
    assert response.headers[AI_ERROR_HEADER] == "busy"


def test_a_provider_400_never_prints_the_status_back(monkeypatch):
    """The exact failure from the report: a 400 with nothing readable in it."""
    _raising(
        monkeypatch,
        llm.ProviderError("Key 1 (Gemini) failed", kind="key", provider="Gemini"),
    )
    body = client.post(
        "/requirements/story/run", data={"user_story": STORY}, headers=KEYS_HEADER
    ).text
    assert "Your Gemini key was refused" in body
    assert "failed (400)" not in body


def test_the_four_sentences_say_what_to_do_and_never_show_a_code():
    assert ai_error_words("key", "Gemini") == (
        "Your Gemini key was refused. Check it in Keys, or try your other key."
    )
    assert ai_error_words("key") == (
        "Your key was refused. Check it in Keys, or try your other key."
    )
    assert ai_error_words("busy") == (
        "The AI is busy. Try again in a minute, or add another key."
    )
    assert ai_error_words("server") == (
        "Something went wrong on our side. Try again in a minute."
    )
    for kind in ("key", "busy", "server", "model", "output", ""):
        said = ai_error_words(kind)
        assert not re.search(r"\d{3}", said), said
        assert "{" not in said


def test_a_status_only_reason_is_dropped_rather_than_shown():
    assert llm.clean_reason("Error code: 400", "") == ""
    assert llm.clean_reason("Error code: 400 - {}", "") == ""
    # A real sentence from the provider still comes through.
    assert "model is overloaded" in llm.clean_reason(
        'Error code: 400 - {"error": {"message": "the model is overloaded"}}', ""
    )


def test_the_browser_has_one_helper_for_every_ai_failure():
    """One shared helper, loaded on every page, used by htmx and by fetch."""
    helper = (ROOT / "public" / "ai_errors.js").read_text(encoding="utf-8")
    base = (ROOT / "qagenius" / "templates" / "base.html").read_text(encoding="utf-8")
    assert '<script src="/ai_errors.js" defer></script>' in base
    for event in ("htmx:responseError", "htmx:sendError", "htmx:timeout"):
        assert event in helper
    assert "fromFetch" in helper
    for desk_js in ("risk_radar.js", "test_matrix.js"):
        source = (ROOT / "public" / desk_js).read_text(encoding="utf-8")
        assert "QAGAiError.fromFetch" in source


@pytest.mark.parametrize(
    "path,title",
    [
        ("qagenius/templates/story.html", "Could not check the story"),
        ("qagenius/templates/story.html", "Could not run the two-reader check"),
        ("qagenius/templates/_risk_radar_result.html", "Could not write a test"),
    ],
)
def test_each_desk_names_its_failure_on_the_button(path, title):
    source = (ROOT / path).read_text(encoding="utf-8")
    assert f'data-error-title="{title}"' in source


# ── Task 5: the matrix asks the AI only when you click ───────────────────


def test_opening_the_matrix_draws_it_without_asking_the_ai(monkeypatch):
    """Opening this desk used to POST /suggest, spending a key every visit."""
    called = []

    def fake(*args, **kwargs):
        called.append(1)
        raise AssertionError("the AI was called on a page load")

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post("/requirements/matrix/editor", data={})
    assert response.status_code == 200
    assert "Suggest from my story" in response.text
    assert "matrix-factor-list" in response.text
    assert not called


def test_the_matrix_page_load_never_posts_to_suggest():
    source = (ROOT / "public" / "test_matrix.js").read_text(encoding="utf-8")
    start = source.split('document.addEventListener("DOMContentLoaded"', 1)[1]
    assert "/requirements/matrix/suggest" not in start
    assert "draw(saved)" in start
    assert "draw(null)" in start


def test_suggested_rules_survive_a_rebuild_and_a_reload():
    """They were drawn once and lost, so seeing them again cost another call."""
    body = {
        "factors": [
            {"name": "Browser", "values": ["Chrome", "Safari"]},
            {"name": "Device", "values": ["Phone", "Desktop"]},
        ],
        "rules": [],
        "pinned": [],
        "reasons": {},
        "from_ai": True,
        "suggested": [
            {
                "if_factor": "Browser",
                "if_value": "Safari",
                "then_factor": "Device",
                "then_value": "Desktop",
                "reason": "Aurora Storefront has no Safari desktop users.",
                "source": "ai",
            }
        ],
    }
    built = client.post("/requirements/matrix/build", json=body)
    assert built.status_code == 200
    data = json.loads(
        re.search(
            r'<script type="application/json" id="matrix-data">(.*?)</script>',
            built.text,
            re.DOTALL,
        ).group(1)
    )
    assert data["suggested"][0]["if_value"] == "Safari"

    # The browser saves that block and hands it back on the next page load.
    again = client.post(
        "/requirements/matrix/editor", data={"saved_json": json.dumps(data)}
    )
    assert "Suggested rules" in again.text
    assert "Aurora Storefront has no Safari desktop users." in again.text


# ── Task 4: "Write a test" links to its own risk ─────────────────────────


def test_a_test_written_for_a_risk_is_never_handed_to_another_one():
    """Write a test on R6 added TC-014; after a reload R1 claimed it."""
    from qagenius.models import RiskAnalysis
    from qagenius.risk_radar import renumbered, retag, risk_tags, score_risks
    from tests.factories import case
    from tests.test_risk_radar import mode

    # R1 is the risk whose words overlap; R6 is the one the test was for.
    race = mode(
        "R6",
        title="Race condition between two sign-in requests",
        cause="Two requests read the counter at the same time",
        effect="The limit is passed",
    )
    counter = mode(
        "R1",
        title="Lockout counter not shared across servers",
        covered_by=["TC-014"],
    )
    written = case(
        case_id="TC-014",
        title="Two sign-ins at once pass the lockout counter",
        tags=["risk:R6"],
        steps=["Send two failed sign-ins at the same time"],
        expected_result="The counter still locks the account",
    )
    report = score_risks(RiskAnalysis(failure_modes=[counter, race]), [written])
    by_id = {item.risk.id: item for item in report.risks}
    assert by_id["R6"].coverage == "verified"
    assert [row[0] for row in by_id["R6"].covered_tests] == ["TC-014"]
    assert by_id["R1"].coverage == "none"
    assert by_id["R1"].covered_tests == []
    assert risk_tags(written) == {"R6"}

    # And it follows its risk when the list is renumbered.
    before = RiskAnalysis(failure_modes=[counter, race])
    after = RiskAnalysis(
        failure_modes=[
            race.model_copy(update={"id": "R1"}),
            counter.model_copy(update={"id": "R2"}),
        ]
    )
    moved = renumbered(before, after)
    assert moved == {"R6": "R1", "R1": "R2"}
    moved_cases = retag([written], moved)
    assert moved_cases[0].tags == ["risk:R1"]
    again = score_risks(after, moved_cases)
    assert {item.risk.id: item.coverage for item in again.risks}["R1"] == "verified"


def test_every_case_from_one_risks_button_carries_that_risks_tag():
    from qagenius.test_case_refine import add_risk_tags
    from tests.factories import case, suite

    current = suite(case(case_id="TC-001"))
    proposed = suite(
        case(case_id="TC-001"),
        case(case_id="TC-014", title="Two sign-ins at once", tags=[]),
    )
    merged = add_risk_tags(current, proposed, ["R6"])
    assert "risk:R6" in merged.test_cases[1].tags


def test_writing_for_several_risks_tags_each_case_with_its_own():
    from qagenius.test_case_refine import add_risk_tags
    from tests.factories import case, suite

    current = suite(case(case_id="TC-001"))
    proposed = suite(
        case(case_id="TC-001"),
        case(case_id="TC-014", title="Covers R6", tags=[]),
        case(case_id="TC-015", title="Covers R3", tags=[]),
    )
    merged = add_risk_tags(current, proposed, ["R6", "R3"])
    assert merged.test_cases[1].tags == ["risk:R6"]
    assert merged.test_cases[2].tags == ["risk:R3"]
