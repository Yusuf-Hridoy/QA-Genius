"""Duel route tests. The duel runner is faked; no network."""

import json

from fastapi.testclient import TestClient

import main
from qagenius import duel as duel_module
from qagenius import llm
from qagenius.duel import DuelResult, build_highlights
from qagenius.models import DuelComparison, Fork, Interpretation

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
