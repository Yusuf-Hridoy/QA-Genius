"""Every desk names the thing it could not do, in its own words.

A reader who asked for test cases and got "Could not check the story" has to
work out which page they are even on. The LLM is faked; no network.
"""

import json

import pytest
from fastapi.testclient import TestClient

import main
from qagenius import llm

client = TestClient(main.app)

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

# One POST per desk that calls the AI, and the title it must show.
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

BUSY_NOTES = [
    "Key 1 (Gemini) was busy (too many requests)",
    "Key 2 (Groq) couldn't give a structured answer",
]


@pytest.fixture
def all_keys_busy(monkeypatch):
    def fake(*args, **kwargs):
        raise llm.AllKeysBusyError(list(BUSY_NOTES))

    monkeypatch.setattr(llm, "generate_json", fake)


@pytest.mark.parametrize("path,form,title", DESKS)
def test_each_desk_names_its_own_failure(all_keys_busy, path, form, title) -> None:
    body = client.post(path, data=form, headers=KEYS_HEADER).text
    assert f"<h2>{title}</h2>" in body


@pytest.mark.parametrize("path,form,title", DESKS)
def test_the_reason_for_every_key_is_listed_in_plain_words(
    all_keys_busy, path, form, title
) -> None:
    body = client.post(path, data=form, headers=KEYS_HEADER).text
    assert "was busy (too many requests)" in body
    assert "couldn&#39;t give a structured answer" in body
    assert "Try again in a minute, or add another key." in body


@pytest.mark.parametrize("path,form,title", DESKS)
def test_no_raw_provider_json_reaches_the_page(monkeypatch, path, form, title) -> None:
    raw = '{"error": {"message": "Failed to validate JSON", "code": 400}}'

    def fake(*args, **kwargs):
        raise llm.ProviderError(f"Key 2 (Groq) failed (400): {llm.clean_reason(raw, '')}")

    monkeypatch.setattr(llm, "generate_json", fake)
    body = client.post(path, data=form, headers=KEYS_HEADER).text
    card = body.split("error-card", 1)[1]
    assert "{" not in card
    assert "Failed to validate JSON" in card
    assert f"<h2>{title}</h2>" in body
