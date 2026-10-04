"""Rotation tests with fake clients. No network."""

import httpx
import openai
import pytest
from pydantic import BaseModel

from qagenius import llm
from qagenius.models import AmbiguityAnalysis


class OkSchema(BaseModel):
    ok: bool


def _http_error(cls: type, status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    return cls(
        "provider said no",
        response=httpx.Response(status, request=request),
        body=None,
    )


class _FakeCompletions:
    def __init__(self, behavior) -> None:
        self.behavior = behavior

    def create(self, **kwargs):
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return self.behavior


class _FakeClient:
    def __init__(self, behavior) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(behavior)})()


def _ok_completion(content: str):
    message = type("Message", (), {"content": content})()
    choice = type("Choice", (), {"message": message})()
    return type("Completion", (), {"choices": [choice]})()


KEYS = [
    {"provider": "gemini", "key": "first", "label": "", "model": "gemini-test-model"},
    {"provider": "groq", "key": "second", "label": "", "model": "groq-test-model"},
]

FIRST_LABEL = "Key 1 (Gemini, gemini-test-model)"
SECOND_LABEL = "Key 2 (Groq, groq-test-model)"


def test_rate_limit_moves_to_next_key() -> None:
    calls = []

    def factory(base_url: str, api_key: str):
        calls.append(api_key)
        if len(calls) == 1:
            return _FakeClient(_http_error(openai.RateLimitError, 429))
        return _FakeClient(_ok_completion('{"ok": true}'))

    result, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True
    assert used == 1
    assert notes == [
        f"{FIRST_LABEL} was busy, trying the next key",
        f"Used {SECOND_LABEL}",
    ]


def test_auth_error_marks_key_invalid_and_moves_on() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.AuthenticationError, 401))
        return _FakeClient(_ok_completion('{"ok": true}'))

    _, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert used == 1
    assert notes[0] == f"{FIRST_LABEL} looked invalid, trying the next key"
    assert notes[-1] == f"Used {SECOND_LABEL}"


def test_all_keys_failing_raises_all_keys_busy() -> None:
    def factory(base_url: str, api_key: str):
        return _FakeClient(_http_error(openai.RateLimitError, 429))

    with pytest.raises(llm.AllKeysBusyError):
        llm.generate_json(KEYS, "system", "user", OkSchema, client_factory=factory)


def test_final_note_names_answering_key() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.RateLimitError, 429))
        return _FakeClient(_ok_completion('{"ok": true}'))

    _, _, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert notes[-1] == f"Used {SECOND_LABEL}"


def test_first_key_success_leaves_notes_empty() -> None:
    def factory(base_url: str, api_key: str):
        return _FakeClient(_ok_completion('{"ok": true}'))

    _, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert used == 0
    assert notes == []


def test_json_repair_handles_fenced_json() -> None:
    def factory(base_url: str, api_key: str):
        return _FakeClient(_ok_completion('```json\n{"ok": true}\n```'))

    result, _, _ = llm.generate_json(
        [KEYS[0]], "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True


def _chat_success_payload(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1720000000,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_busy_key_is_called_exactly_once() -> None:
    """A 429 must not be retried by the SDK: one request, then the next key."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        if len(seen) == 1:
            return httpx.Response(
                429, json={"error": {"message": "rate limited", "type": "x"}}
            )
        return httpx.Response(200, json=_chat_success_payload('{"ok": true}'))

    def factory(base_url: str, api_key: str):
        client = llm.default_client_factory(base_url, api_key)
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        return client

    result, used, _ = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True
    assert used == 1
    first_key_calls = [h for h in seen if h == "Bearer first"]
    assert len(first_key_calls) == 1
    assert len(seen) == 2


def test_system_without_placeholder_still_carries_schema() -> None:
    received: dict = {}

    class RecordingCompletions:
        def create(self, **kwargs):
            received.update(kwargs)
            message = type("Message", (), {"content": '{"ok": true}'})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class RecordingClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": RecordingCompletions()})()

    with pytest.raises(llm.BadOutputError):
        # '{"ok": true}' cannot validate as AmbiguityAnalysis, but the
        # system message must already contain the schema by then.
        llm.generate_json(
            [KEYS[0]],
            "You are a requirements auditor.",
            "Some story.",
            AmbiguityAnalysis,
            client_factory=lambda base_url, api_key: RecordingClient(),
        )
    system_text = received["messages"][0]["content"]
    assert "ambiguity_score" in system_text
    assert '"properties"' in system_text


def test_model_not_available_moves_to_next_key() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.NotFoundError, 404))
        return _FakeClient(_ok_completion('{"ok": true}'))

    result, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True
    assert used == 1
    assert "not available" in notes[0]
    assert "gemini-test-model" in notes[0]
    assert notes[-1] == f"Used {SECOND_LABEL}"


def test_all_models_unavailable_raises_model_unavailable() -> None:
    def factory(base_url: str, api_key: str):
        return _FakeClient(_http_error(openai.NotFoundError, 404))

    with pytest.raises(llm.ModelUnavailableError) as exc_info:
        llm.generate_json(KEYS, "system", "user", OkSchema, client_factory=factory)
    assert len(exc_info.value.notes) == 2
    assert all("not available" in note for note in exc_info.value.notes)


def test_mixed_unavailable_and_busy_raises_all_keys_busy() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.NotFoundError, 404))
        return _FakeClient(_http_error(openai.RateLimitError, 429))

    with pytest.raises(llm.AllKeysBusyError):
        llm.generate_json(KEYS, "system", "user", OkSchema, client_factory=factory)


def test_entry_model_is_sent_to_provider() -> None:
    received: dict = {}

    class RecordingCompletions:
        def create(self, **kwargs):
            received.update(kwargs)
            return _ok_completion('{"ok": true}')

    class RecordingClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": RecordingCompletions()})()

    result, used, _ = llm.generate_json(
        [KEYS[0]],
        "system",
        "user",
        OkSchema,
        client_factory=lambda base_url, api_key: RecordingClient(),
    )
    assert result.ok is True
    assert used == 0
    assert received["model"] == "gemini-test-model"


def test_unsafe_model_falls_back_to_live_list() -> None:
    received: dict = {}
    fetches: list[str] = []

    class RecordingCompletions:
        def create(self, **kwargs):
            received.update(kwargs)
            return _ok_completion('{"ok": true}')

    class RecordingClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": RecordingCompletions()})()

    def fetcher(base_url: str, api_key: str):
        fetches.append(base_url)
        return ["whatever-flash-model"]

    keys = [{"provider": "gemini", "key": "k", "model": "evil; touch /tmp/x"}]
    result, _, notes = llm.generate_json(
        keys,
        "system",
        "user",
        OkSchema,
        client_factory=lambda base_url, api_key: RecordingClient(),
        models_fetcher=fetcher,
    )
    assert result.ok is True
    assert received["model"] == "whatever-flash-model"
    assert fetches == ["https://generativelanguage.googleapis.com/v1beta/openai/"]
    assert notes == []


def test_missing_model_lists_once_per_provider() -> None:
    fetches: list[str] = []

    def fetcher(base_url: str, api_key: str):
        fetches.append(api_key)
        return ["picked-model"]

    def factory(base_url: str, api_key: str):
        if api_key == "one":
            return _FakeClient(_http_error(openai.RateLimitError, 429))
        return _FakeClient(_ok_completion('{"ok": true}'))

    keys = [
        {"provider": "gemini", "key": "one"},
        {"provider": "gemini", "key": "two"},
    ]
    _, used, _ = llm.generate_json(
        keys,
        "system",
        "user",
        OkSchema,
        client_factory=factory,
        models_fetcher=fetcher,
    )
    assert used == 1
    assert fetches == ["one"]


def test_no_credit_moves_to_next_key() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.APIStatusError, 402))
        return _FakeClient(_ok_completion('{"ok": true}'))

    result, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True
    assert used == 1
    assert notes == [
        f"{FIRST_LABEL} has no credit for this model, trying the next key",
        f"Used {SECOND_LABEL}",
    ]
