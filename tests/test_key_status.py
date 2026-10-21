"""The key panel says what the last real AI call did, not what Test said.

The server never stores a key, so only the browser can remember how each one
did. Every request reports its results by position in a header, and app.js
writes them into the panel. No key is ever in that header.
"""

import json
from pathlib import Path

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.web import KEY_RESULTS_HEADER

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parent.parent

KEY_A = "sk-first-key-never-logged"
KEY_B = "sk-second-key-never-logged"
KEYS_HEADER = {
    "X-QAG-Keys": json.dumps(
        [
            {"provider": "gemini", "key": KEY_A, "model": "m1"},
            {"provider": "groq", "key": KEY_B, "model": "m2"},
        ]
    )
}
STORY = {"user_story": "As a shopper, I want to sign in so that I can buy."}

ANALYSIS = {
    "ambiguity_score": 20,
    "clarity_label": "Mostly clear",
    "invest_overall": "PASS",
    "invest_independent": "PASS",
    "invest_negotiable": "PASS",
    "invest_valuable": "PASS",
    "invest_estimable": "PASS",
    "invest_small": "PASS",
    "invest_testable": "PASS",
    "vague_phrases": [],
    "missing_elements": [],
    "suggested_rewrites": [],
    "generated_acceptance_criteria": ["The shopper can sign in"],
    "risks": [],
}


class _Completions:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def create(self, **kwargs):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        message = type("Message", (), {"content": self.behaviour})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()


class _Client:
    def __init__(self, behaviour):
        self.chat = type("Chat", (), {"completions": _Completions(behaviour)})()


def _busy() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    return openai.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None
    )


@pytest.fixture
def first_busy(monkeypatch):
    def factory(base_url: str, api_key: str):
        if api_key == KEY_A:
            return _Client(_busy())
        return _Client(json.dumps(ANALYSIS))

    real = llm.generate_json

    def patched(keys, system, user, schema, **kwargs):
        return real(keys, system, user, schema, client_factory=factory)

    monkeypatch.setattr(llm, "generate_json", patched)


def _results(response) -> list[dict]:
    raw = response.headers.get(KEY_RESULTS_HEADER)
    assert raw, "the response carries no key results"
    return json.loads(raw)


def test_a_real_run_says_what_each_key_did(first_busy):
    response = client.post(
        "/requirements/story/run", data=STORY, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    assert _results(response) == [
        {"index": 0, "ok": False, "reason": "busy (too many requests)"},
        {"index": 1, "ok": True, "reason": ""},
    ]


def test_the_header_never_carries_a_key(first_busy):
    response = client.post(
        "/requirements/story/run", data=STORY, headers=KEYS_HEADER
    )
    raw = response.headers[KEY_RESULTS_HEADER]
    assert KEY_A not in raw
    assert KEY_B not in raw


def test_a_page_that_calls_no_ai_reports_nothing():
    assert KEY_RESULTS_HEADER not in client.get("/requirements/story").headers


def test_the_browser_writes_those_results_into_the_panel():
    app_js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    assert f'var KEY_RESULTS_HEADER = "{KEY_RESULTS_HEADER}"' in app_js
    assert "applyKeyResults(xhr.getResponseHeader(KEY_RESULTS_HEADER))" in app_js
    # It writes the same shape the Test button writes.
    block = app_js.split("function applyKeyResults(", 1)[1].split("\n  }", 1)[0]
    assert "lastTest" in block
    assert "storeKeys(keys)" in block


def test_the_chip_only_says_connected_for_a_key_that_answered():
    app_js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    block = app_js.split("function updateChip(", 1)[1].split("\n  }", 1)[0]
    assert "Key problem — open to check" in block
    # "connected" is only reachable through a key whose last result was ok.
    before = block.split('" connected · "', 1)[0]
    assert "if (working) {" in before
