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
# The sentence a user reads leaves the model id off: it is in the key panel,
# and it is not what the line is telling them.
ANSWERED = "Key 2 (Groq) answered."


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
    assert notes == [f"{FIRST_LABEL} was busy (too many requests), so {ANSWERED}"]


def test_auth_error_marks_key_invalid_and_moves_on() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_http_error(openai.AuthenticationError, 401))
        return _FakeClient(_ok_completion('{"ok": true}'))

    _, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert used == 1
    assert notes == [f"{FIRST_LABEL} looked invalid, so {ANSWERED}"]


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
    assert notes == [f"{FIRST_LABEL} was busy (too many requests), so {ANSWERED}"]


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
    assert notes[0].endswith(f"so {ANSWERED}")


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
    assert notes == [f"{FIRST_LABEL} has no credit for this model, so {ANSWERED}"]


# ── a provider that refuses the way we ask for JSON ──────────────────────────


class _JsonModeRefuser:
    """A provider that answers only when response_format is left off.

    Groq's openai/gpt-oss-20b did exactly this in a real run: every
    structured call came back "400 Failed to validate JSON".
    """

    def __init__(self, content: str = '{"ok": true}') -> None:
        self.calls: list[bool] = []
        self.content = content
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        used_json_mode = "response_format" in kwargs
        self.calls.append(used_json_mode)
        if used_json_mode:
            request = httpx.Request("POST", "https://provider.test/v1/chat")
            raise openai.BadRequestError(
                "Failed to validate JSON",
                response=httpx.Response(400, request=request),
                body=None,
            )
        return _ok_completion(self.content)


def test_a_400_about_json_retries_the_same_key_without_json_mode() -> None:
    refuser = _JsonModeRefuser()
    result, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema,
        client_factory=lambda base_url, api_key: refuser,
    )
    assert result.ok is True
    # The first key answered: no second key was needed.
    assert used == 0
    assert notes == []
    assert refuser.calls == [True, False]


def test_the_schema_is_still_in_the_prompt_on_the_plain_retry() -> None:
    seen: list[str] = []

    class Recorder(_JsonModeRefuser):
        def create(self, **kwargs):
            seen.append(kwargs["messages"][0]["content"])
            return super().create(**kwargs)

    llm.generate_json(
        KEYS, "system", "user", OkSchema,
        client_factory=lambda base_url, api_key: Recorder(),
    )
    assert all('"properties"' in text for text in seen)


def test_a_key_that_cannot_hold_a_shape_hands_over_to_the_next_one() -> None:
    def factory(base_url: str, api_key: str):
        if api_key == "first":
            return _FakeClient(_ok_completion("I am afraid I cannot do that."))
        return _FakeClient(_ok_completion('{"ok": true}'))

    result, used, notes = llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=factory
    )
    assert result.ok is True
    assert used == 1
    assert "couldn't give a structured answer" in notes[0]


def test_every_key_failing_the_shape_is_its_own_error() -> None:
    def factory(base_url: str, api_key: str):
        return _FakeClient(_ok_completion("not json at all"))

    with pytest.raises(llm.BadOutputError) as caught:
        llm.generate_json(KEYS, "system", "user", OkSchema, client_factory=factory)
    assert len(caught.value.notes) == 2
    assert all("structured answer" in note for note in caught.value.notes)


# ── provider reasons are short, plain and never raw JSON ─────────────────────


def test_a_json_error_body_is_shown_as_its_one_readable_line() -> None:
    body = '{"error": {"message": "the model is retired", "type": "invalid"}}'
    said = llm.clean_reason(body, "")
    assert said == "the model is retired"
    assert "{" not in said


def test_a_long_reason_is_cut_at_a_word() -> None:
    said = llm.clean_reason("word " * 60, "")
    assert len(said) <= llm.REASON_LIMIT + 1
    assert said.endswith("…")
    assert "wor…" not in said


def test_a_reason_never_shows_the_key() -> None:
    said = llm.clean_reason("rejected key sk-abcdefghijklmnopqrstuvwxyz", "")
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in said
    assert "[hidden]" in said
