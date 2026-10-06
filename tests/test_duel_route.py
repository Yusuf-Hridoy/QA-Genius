"""Duel route tests. The duel runner is faked; no network."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius import duel as duel_module
from qagenius import llm
from qagenius.duel import NOT_STATED_B, DuelResult, build_highlights, ground_forks
from qagenius.models import DuelComparison, Fork, Interpretation, NumberReading
from qagenius.numbers import match_numbers
from qagenius.vague import find_vague_words

client = TestClient(main.app)

KEYS_HEADER = {
    "X-QAG-Keys": json.dumps([{"provider": "gemini", "key": "first"}])
}

FORM = {"user_story": "As a shopper, I want my account to lock quickly."}

STORY = "As a shopper, I want my account to lock quickly after too many attempts."


def _fake_result(story=STORY):
    reading_a = Interpretation(
        rules=[{"topic": "Speed", "reading": "locks fast", "source_phrase": "quickly"}],
        numbers=[{"name": "Attempts", "value": "3", "source_phrase": "too many"}],
    )
    reading_b = Interpretation(
        rules=[{"topic": "Speed", "reading": "locks slowly", "source_phrase": "quickly"}],
        numbers=[{"name": "Attempts", "value": "10", "source_phrase": "too many"}],
    )
    comparison = DuelComparison(
        forks=[
            Fork(
                topic="Speed",
                reading_a="locks fast",
                reading_b="locks slowly",
                source_phrase="quickly",
                severity="high",
                suggested_rewrite="within 60 seconds",
            )
        ],
        agreements=["Both agree on the actor."],
    )
    return DuelResult(
        reading_a=reading_a,
        reading_b=reading_b,
        comparison=comparison,
        agreement_pct=50,
        highlights=build_highlights(story, comparison.forks),
        notes=["Used Key 1 (Gemini)"],
        provider_name="Gemini",
        used_index=0,
    )


def test_duel_no_keys_signals_drawer_open() -> None:
    response = client.post("/requirements/story/duel", data=FORM)
    assert response.status_code == 200
    assert response.headers.get("hx-trigger") == "open-keys"


def test_fake_duel_returns_duel_card(monkeypatch) -> None:
    def fake(keys, user_story, story_type, context):
        assert "quickly" in user_story
        return _fake_result(user_story)

    monkeypatch.setattr(duel_module, "run_duel", fake)
    response = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    body = response.text
    assert "fork-mark" in body
    assert "agreement" in body
    assert "Reader A" in body
    assert "Reader B" in body
    assert "Apply rewrite" in body
    assert "Answered by" in body


def test_load_example_includes_duel_without_key() -> None:
    response = client.get("/requirements/story/example")
    assert response.status_code == 200
    body = response.text
    assert "Ambiguity duel" in body
    assert "fork-mark" in body
    assert "Clarity score" in body


def test_duel_error_renders_error_card(monkeypatch) -> None:
    def fake(keys, user_story, story_type, context):
        raise llm.AllKeysBusyError([])

    monkeypatch.setattr(duel_module, "run_duel", fake)
    response = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    )
    assert "All your keys are busy" in response.text


def test_side_by_side_tables_removed(monkeypatch) -> None:
    monkeypatch.setattr(
        duel_module, "run_duel", lambda k, s, t, c: _fake_result(s)
    )
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Rules side by side" not in body
    assert "Numbers side by side" not in body


def test_not_stated_rendered_muted(monkeypatch) -> None:
    def fake(keys, user_story, story_type, context):
        result = _fake_result(user_story)
        fork = result.comparison.forks[0]
        result.comparison.forks[0] = fork.model_copy(
            update={"reading_b": NOT_STATED_B}
        )
        return result

    monkeypatch.setattr(duel_module, "run_duel", fake)
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert '<em class="muted">not stated by Reader B</em>' in body


def test_vague_rewrite_disables_apply(monkeypatch) -> None:
    def fake(keys, user_story, story_type, context):
        result = _fake_result(user_story)
        result.vague_rewrites = {0: ["quickly"]}
        return result

    monkeypatch.setattr(duel_module, "run_duel", fake)
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert "still vague: quickly" in body
    assert re.search(r"<button[^>]*apply-rewrite[^>]*disabled", body)


def test_removed_claims_line(monkeypatch) -> None:
    def fake(keys, user_story, story_type, context):
        result = _fake_result(user_story)
        result.removed_claims = 2
        return result

    monkeypatch.setattr(duel_module, "run_duel", fake)
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Removed 2 claim(s)" in body


def test_sample_duel_is_clean() -> None:
    sample = json.loads(
        Path("qagenius/samples/duel.json").read_text(encoding="utf-8")
    )
    reading_a = Interpretation.model_validate(sample["reading_a"])
    reading_b = Interpretation.model_validate(sample["reading_b"])
    comparison = DuelComparison.model_validate(sample["comparison"])
    assert len(reading_a.numbers) >= 3
    assert len(reading_a.rules) >= 3
    assert len(reading_b.numbers) >= 3
    assert len(reading_b.rules) >= 3
    _, removed, _ = ground_forks(comparison, reading_a, reading_b)
    assert removed == 0
    for fork in comparison.forks:
        assert find_vague_words(fork.suggested_rewrite) == []


def _matched_result(story=STORY):
    """A result whose readers gave the numbers from a real Gemini run."""
    reading_a = Interpretation(
        numbers=[
            NumberReading(
                name="Lockout Response Time", value="1 second", source_phrase="quickly"
            ),
            NumberReading(
                name="Account Lockout Duration",
                value="30 minutes",
                source_phrase="lock",
            ),
        ]
    )
    reading_b = Interpretation(
        numbers=[
            NumberReading(
                name="Lock execution time limit",
                value="3 seconds",
                source_phrase="quickly",
            ),
            NumberReading(
                name="Account lockout duration",
                value="30 minutes",
                source_phrase="lock",
            ),
        ]
    )
    comparison = DuelComparison(forks=[], agreements=["Both agree on the actor."])
    return DuelResult(
        reading_a=reading_a,
        reading_b=reading_b,
        comparison=comparison,
        agreement_pct=50,
        highlights=build_highlights(story, comparison.forks),
        notes=[],
        provider_name="Gemini",
        used_index=0,
        number_matches=match_numbers(reading_a, reading_b),
    )


def test_values_table_rendered(monkeypatch) -> None:
    monkeypatch.setattr(
        duel_module, "run_duel", lambda k, s, t, c: _matched_result(s)
    )
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Values compared by code" in body
    assert "1 second" in body
    assert "3 seconds" in body
    assert '<span class="pill bad">different</span>' in body
    assert '<span class="pill ok">same</span>' in body
    assert "Matched by unit and name, not by AI." in body


def test_values_table_hidden_when_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        duel_module, "run_duel", lambda k, s, t, c: _fake_result(s)
    )
    body = client.post(
        "/requirements/story/duel", data=FORM, headers=KEYS_HEADER
    ).text
    assert "Values compared by code" not in body
    assert "Matched by unit and name, not by AI." not in body


def test_load_example_has_values_table() -> None:
    body = client.get("/requirements/story/example").text
    assert "Values compared by code" in body
    assert '<span class="pill ok">same</span>' in body
    assert '<span class="pill bad">different</span>' in body
