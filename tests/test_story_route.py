"""Story route tests. The LLM is faked; no network."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from qagenius import llm
from qagenius.models import AmbiguityAnalysis

client = TestClient(main.app)

SAMPLE = json.loads(
    Path("qagenius/samples/story_check.json").read_text(encoding="utf-8")
)
FAKE_RESULT = AmbiguityAnalysis.model_validate(SAMPLE["result"])

KEYS_HEADER = {
    "X-QAG-Keys": json.dumps(
        [
            {"provider": "gemini", "key": "first"},
            {"provider": "groq", "key": "second"},
        ]
    )
}

FORM = {"user_story": "As a shopper, I want my account to lock quickly."}


def test_no_keys_returns_key_panel() -> None:
    response = client.post("/requirements/story/run", data=FORM)
    assert response.status_code == 200
    body = response.text
    assert "Save and generate" in body
    assert "panel-key" in body
    assert "Get a free" in body


def test_fake_llm_returns_result_cards(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        assert "quickly" in user
        return FAKE_RESULT, 1, ["Key 1 (Gemini) was busy, trying the next key", "Used Key 2 (Groq)"]

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    body = response.text
    assert "Clarity score" in body
    assert "48" in body  # 100 - sample ambiguity_score 52
    assert "<mark>quickly</mark>" in body
    assert "Scenario:" in body
    assert "Answered by Groq (free)" in body


def test_load_example_needs_no_keys() -> None:
    response = client.get("/requirements/story/example")
    assert response.status_code == 200
    body = response.text
    assert "Clarity score" in body
    assert "<mark>" in body
    assert "Scenario:" in body


def test_busy_keys_return_plain_error(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        raise llm.AllKeysBusyError([])

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert "All your keys are busy" in response.text


def test_invalid_key_returns_plain_error(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        raise llm.InvalidKeyError([])

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert "was rejected" in response.text


def test_unreadable_output_returns_plain_error(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        raise llm.BadOutputError("The AI returned something unreadable. Try again.")

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert "unreadable" in response.text


def test_unavailable_model_returns_update_message(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        raise llm.ModelUnavailableError(
            ['Key 1 (Gemini): the model "gemini-x" is not available']
        )

    monkeypatch.setattr(llm, "generate_json", fake)
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    body = response.text
    assert "Your keys are fine" in body
    assert "needs a model update" in body
    assert "not available" in body


def test_story_run_sends_schema_to_model(monkeypatch) -> None:
    received: dict = {}

    class RecordingCompletions:
        def create(self, **kwargs):
            received.update(kwargs)
            message = type("Message", (), {"content": json.dumps(SAMPLE["result"])})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class RecordingClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": RecordingCompletions()})()

    monkeypatch.setattr(
        llm, "default_client_factory", lambda base_url, api_key: RecordingClient()
    )
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    system_text = received["messages"][0]["content"]
    assert "ambiguity_score" in system_text
    assert '"properties"' in system_text
