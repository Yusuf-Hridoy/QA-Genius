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


def test_no_keys_signals_drawer_open() -> None:
    response = client.post("/requirements/story/run", data=FORM)
    assert response.status_code == 200
    assert response.headers.get("hx-trigger") == "open-keys"


def test_malformed_keys_header_signals_drawer_open() -> None:
    response = client.post(
        "/requirements/story/run",
        data=FORM,
        headers={"X-QAG-Keys": "not-json"},
    )
    assert response.status_code == 200
    assert response.headers.get("hx-trigger") == "open-keys"


def test_unsafe_model_is_dropped_from_header(monkeypatch) -> None:
    seen: dict = {}

    def fake(keys, system, user, schema):
        seen["keys"] = keys
        return FAKE_RESULT, 0, []

    monkeypatch.setattr(llm, "generate_json", fake)
    header = {
        "X-QAG-Keys": json.dumps(
            [{"provider": "gemini", "key": "k", "model": "evil; touch /tmp/x"}]
        )
    }
    client.post("/requirements/story/run", data=FORM, headers=header)
    assert "model" not in seen["keys"][0]

    header = {
        "X-QAG-Keys": json.dumps(
            [{"provider": "gemini", "key": "k", "model": "gemini-3.8-flash"}]
        )
    }
    client.post("/requirements/story/run", data=FORM, headers=header)
    assert seen["keys"][0]["model"] == "gemini-3.8-flash"


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
    monkeypatch.setattr(
        llm, "list_chat_models", lambda provider, key, fetcher=None: ["schema-model"]
    )
    response = client.post(
        "/requirements/story/run", data=FORM, headers=KEYS_HEADER
    )
    assert response.status_code == 200
    system_text = received["messages"][0]["content"]
    assert "ambiguity_score" in system_text
    assert '"properties"' in system_text


def test_story_result_carries_criteria_to_step_two(monkeypatch) -> None:
    """The Use these criteria button and its JSON ride along with the result."""
    body = client.get("/requirements/story/example").text
    assert 'id="use-criteria"' in body
    assert '<script type="application/json" id="story-criteria">' in body
    raw = body.split('<script type="application/json" id="story-criteria">')[1]
    raw = raw.split("</script>")[0]
    criteria = json.loads(raw)
    assert isinstance(criteria, list)
    assert len(criteria) >= 1
    assert all(isinstance(text, str) for text in criteria)


def test_story_criteria_json_is_escaped_not_safe() -> None:
    """tojson must escape a closing tag so AI text cannot break out of the script."""
    body = client.get("/requirements/story/example").text
    block = body.split('id="story-criteria">')[1].split("</script>")[0]
    assert "</script" not in block
