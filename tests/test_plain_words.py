"""Plain words: what the AI is asked for, and what the screens say.

Two guards. The first is that every AI call asks for sentences a new tester
can read. The second is that no page shows a word someone would have to look
up -- the words a QA tool reaches for by habit, which mean nothing to a
tester in their first month or reading English as a second language.
"""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import (
    AmbiguityAnalysis,
    DuelComparison,
    Interpretation,
    MatrixProposal,
    ProposedFactor,
    RiskAnalysis,
)
from qagenius.duel import run_duel
from qagenius.prompts import PLAIN_WORDS
from tests.factories import (
    LOCKOUT_CRITERIA,
    LOCKOUT_STORY,
    case,
    script,
    suite,
)
from tests.test_risk_radar import mode

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent

KEYS_HEADER = {"X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])}
ASKED = PLAIN_WORDS.strip()

STORY_FORM = {"user_story": LOCKOUT_STORY}
CRITERIA_FORM = {
    "user_story": LOCKOUT_STORY,
    "criteria_json": json.dumps(LOCKOUT_CRITERIA),
}
CASES_FORM = {**CRITERIA_FORM, "coverage_focus": ["Functional", "Negative"]}
RISK_FORM = {**CRITERIA_FORM, "cases_json": json.dumps([case().model_dump()])}


def _fake(answer, calls: list):
    def generate(keys, system, user, schema, **kwargs):
        calls.append(user)
        return answer, 0, []

    return generate


def _by_schema(answers: dict, calls: list):
    """One fake for a route that calls more than one schema, like the duel."""

    def generate(keys, system, user, schema, **kwargs):
        calls.append(user)
        return answers[schema], 0, []

    return generate


# ── every AI call asks for words a new tester can read ───────────────────────


def test_the_story_check_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        llm, "generate_json", _fake(AmbiguityAnalysis.model_construct(
            ambiguity_score=20,
            clarity_label="Clear",
            invest_overall="Good",
            invest_independent="Yes",
            invest_negotiable="Yes",
            invest_valuable="Yes",
            invest_estimable="Yes",
            invest_small="Yes",
            invest_testable="Yes",
            vague_phrases=[],
            missing_elements=[],
            suggested_rewrites=[],
            generated_acceptance_criteria=[],
            risks=[],
        ), calls)
    )
    client.post("/requirements/story/run", data=STORY_FORM, headers=KEYS_HEADER)
    assert calls and all(ASKED in user for user in calls)


def test_the_test_cases_call_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake(suite(case()), calls))
    client.post("/requirements/test-cases/run", data=CASES_FORM, headers=KEYS_HEADER)
    assert calls and all(ASKED in user for user in calls)


def test_the_refine_call_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake(suite(case()), calls))
    client.post(
        "/requirements/test-cases/refine",
        data={
            **CRITERIA_FORM,
            "current_json": suite(case()).model_dump_json(),
            "mode": "instruction",
            "instruction": "Add a case for an unknown email.",
            "coverage_focus": ["Functional"],
        },
        headers=KEYS_HEADER,
    )
    assert calls and all(ASKED in user for user in calls)


def test_the_automation_call_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake(script(), calls))
    client.post(
        "/requirements/automation/run",
        data={
            "selected_json": json.dumps([case().model_dump()]),
            "framework_choice": "Playwright · TypeScript",
            "structure_choice": "Page Object Model",
            "browsers": ["chromium"],
            "base_url": "https://example.com",
        },
        headers=KEYS_HEADER,
    )
    assert calls and all(ASKED in user for user in calls)


def test_the_risk_radar_call_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        llm, "generate_json", _fake(RiskAnalysis(failure_modes=[mode()]), calls)
    )
    client.post("/risks/run", data=RISK_FORM, headers=KEYS_HEADER)
    assert calls and all(ASKED in user for user in calls)


def test_the_test_matrix_call_asks_for_plain_words(monkeypatch) -> None:
    calls: list = []
    proposal = MatrixProposal(
        factors=[
            ProposedFactor(name="Browser", values=["Chrome", "Safari"], reason="Web."),
            ProposedFactor(name="Device", values=["Desktop", "Phone"], reason="Both."),
        ]
    )
    monkeypatch.setattr(llm, "generate_json", _fake(proposal, calls))
    client.post("/requirements/matrix/suggest", data=RISK_FORM, headers=KEYS_HEADER)
    assert calls and all(ASKED in user for user in calls)


def test_all_three_duel_calls_ask_for_plain_words() -> None:
    """Reader A, reader B and the comparison each get the line."""
    calls: list = []
    answers = {
        Interpretation: Interpretation(),
        DuelComparison: DuelComparison(),
    }
    run_duel(
        [{"provider": "gemini", "key": "first"}],
        LOCKOUT_STORY,
        "User story",
        "",
        generate=_by_schema(answers, calls),
    )
    assert len(calls) == 3
    assert all(ASKED in user for user in calls)


def test_the_line_is_appended_and_never_edited_into_the_v1_prompt(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(llm, "generate_json", _fake(suite(case()), calls))
    client.post("/requirements/test-cases/run", data=CASES_FORM, headers=KEYS_HEADER)
    user = calls[0]
    assert user.endswith(ASKED)
    assert user.index("Test Coverage Focus") < user.index(ASKED)


# ── no screen shows a word a new tester would have to look up ────────────────

# Every one of these had a reason to exist and none of them is a word a tester
# says out loud. The replacement for each is in the phase 13 brief.
BANNED = (
    "principal qa",
    "shadow qa",
    "failure mode",
    "rpn",
    "detectability",
    "likelihood",
    "traceability",
    "pairwise",
    "factors",
    "verdict",
    "thin",
    "source card",
    "fingerprint",
    # The words the brief replaced, which a later change could reach for again.
    "vague phrase",
    "fork",
    "ambiguity duel",
    "heat map",
    "impossible combination",
    "manual only",
    "brittle selector",
    "fixed wait",
)

PAGES = (
    "/",
    "/requirements/story",
    "/requirements/criteria",
    "/requirements/test-cases",
    "/requirements/automation",
    "/requirements/matrix",
    "/risks",
    "/ship",
    "/bugs",
    "/insights",
    "/requirements/story/example",
    "/requirements/test-cases/example",
    "/requirements/test-cases/example-strengthen",
    "/requirements/automation/example",
    "/requirements/matrix/example",
    "/risks/example",
    "/ship/example",
    "/bugs/example",
    "/insights/example",
    "/insights/example-explained",
)

_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def visible_text(html: str) -> str:
    """What a reader actually sees: no scripts, no markup, no comments.

    Data blocks are JSON the browser reads back, and a class name is not a
    word on a screen, so neither is read here.
    """
    body = _SCRIPT.sub(" ", html)
    body = _STYLE.sub(" ", body)
    body = _COMMENT.sub(" ", body)
    # A title or aria-label is read out loud, so it counts as visible.
    spoken = " ".join(
        re.findall(r'(?:title|aria-label|placeholder)="([^"]*)"', body)
    )
    return (_TAG.sub(" ", body) + " " + spoken).lower()


def says(text: str, word: str) -> bool:
    """Whole words, plural included.

    "within" is not "thin" and "refactors" is not a factor, but "failure
    modes" is still the word this guard is here to keep off a screen.
    """
    pattern = rf"(?<![\w-]){re.escape(word)}(?:e?s)?(?![\w-])"
    return re.search(pattern, text) is not None


def _page(path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    return visible_text(response.text)


def test_no_page_shows_a_word_a_new_tester_would_look_up() -> None:
    offences: list[str] = []
    for path in PAGES:
        text = _page(path)
        for word in BANNED:
            if says(text, word):
                offences.append(f"{path}: {word}")
    assert offences == []


def test_the_guard_reads_what_a_reader_sees() -> None:
    """The guard would be worthless if it passed on a page that says the word."""
    html = '<p class="rpn">Risk score 48</p><script>var rpn = 48;</script>'
    assert not says(visible_text(html), "rpn")
    assert says(visible_text("<p>RPN 48</p>"), "rpn")
    # "within" is not "thin", and a class name is not a word on a screen.
    assert not says(visible_text("<p>within the hour</p>"), "thin")


# ── the few QA words that stay get a "What's this?" ──────────────────────────

EXPLAINED = (
    "acceptance-criteria",
    "test-case",
    "boundary",
    "negative",
    "edge-case",
    "invest",
    "risk-score",
    "playwright",
    "given-when-then",
    "pairwise",
)


def _dictionary() -> str:
    return (ROOT / "public" / "plain_words.js").read_text(encoding="utf-8")


def test_the_dictionary_is_loaded_on_every_page() -> None:
    base = (ROOT / "qagenius" / "templates" / "base.html").read_text(encoding="utf-8")
    assert '<script src="/plain_words.js" defer></script>' in base


def test_every_explained_word_is_in_the_dictionary() -> None:
    words = _dictionary()
    for key in EXPLAINED:
        assert f"{key}:" in words or f'"{key}"' in words, key


def test_every_mark_in_a_template_names_a_word_the_dictionary_has() -> None:
    words = _dictionary()
    used = set()
    for path in (ROOT / "qagenius" / "templates").glob("*.html"):
        used.update(re.findall(r'data-explain="([^"]+)"', path.read_text(encoding="utf-8")))
    assert used
    for key in sorted(used):
        assert f"{key}:" in words or f'"{key}"' in words, key


def test_each_word_is_explained_somewhere() -> None:
    """A note nobody can reach is a note nobody reads."""
    marked = set()
    for path in (ROOT / "qagenius" / "templates").glob("*.html"):
        marked.update(re.findall(r'data-explain="([^"]+)"', path.read_text(encoding="utf-8")))
    assert set(EXPLAINED) <= marked


def test_the_buttons_reach_the_rendered_pages() -> None:
    pages = {
        "/requirements/criteria": "acceptance-criteria",
        "/requirements/test-cases": "test-case",
        "/requirements/automation": "playwright",
    }
    for path, key in pages.items():
        assert f'data-explain="{key}"' in client.get(path).text, path


def test_a_result_card_carries_its_own_marks() -> None:
    body = client.get("/requirements/test-cases/example").text
    assert 'data-explain="boundary"' in body
    assert 'data-explain="negative"' in body


def test_the_note_is_built_with_dom_methods_not_markup() -> None:
    """No innerHTML anywhere: the words are data, never markup."""
    words = _dictionary()
    assert "innerHTML" not in words
    assert "createElement" in words and "textContent" in words


def test_the_button_is_a_button_and_says_whether_it_is_open() -> None:
    words = _dictionary()
    assert 'createElement("button")' in words or 'el("button"' in words
    assert 'setAttribute("aria-expanded"' in words
    assert '"Escape"' in words


def test_the_panel_is_readable_in_both_themes() -> None:
    """It uses the tokens, so dark mode needs no second rule."""
    css = (ROOT / "public" / "style.css").read_text(encoding="utf-8")
    assert ".explain-panel{" in css
    assert "background:var(--card)" in css.replace("\n", "").replace("  ", "")
    assert ".explain-btn:focus-visible{outline" in css
