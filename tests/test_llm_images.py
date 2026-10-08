"""Optional screenshots in AI calls. Fake clients only; no network."""

import logging

import httpx
import openai
import pytest
from pydantic import BaseModel

from qagenius import llm

# A 1x1 PNG. Short, but it must never reach a log.
B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
IMAGE = ("image/png", B64)
KEYS = [{"provider": "gemini", "key": "sk-key", "label": "", "model": "test-model"}]


class OkSchema(BaseModel):
    ok: bool


def _status_error(status: int, message: str) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    response = httpx.Response(status, request=request)
    kinds = {
        400: openai.BadRequestError,
        404: openai.NotFoundError,
        422: openai.UnprocessableEntityError,
    }
    return kinds[status](message, response=response, body=None)


class _FakeClient:
    """Records every messages payload and follows a script of outcomes."""

    def __init__(self, script: list) -> None:
        self.sent: list = []
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.sent.append(kwargs["messages"])
                step = script.pop(0) if script else None
                if isinstance(step, Exception):
                    raise step
                message = type("Message", (), {"content": '{"ok": true}'})()
                choice = type("Choice", (), {"message": message})()
                return type("Completion", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": Completions()})()


def _factory(client: _FakeClient):
    def make(base_url: str, api_key: str):
        return client

    return make


def _user_content(client: _FakeClient, call: int = 0):
    return client.sent[call][1]["content"]


def test_without_an_image_the_user_content_is_a_plain_string() -> None:
    client = _FakeClient([])
    result, index, notes = llm.generate_json(
        KEYS, "system", "user text", OkSchema, client_factory=_factory(client)
    )
    assert result.ok is True
    assert index == 0
    assert notes == []
    assert _user_content(client) == "user text"
    assert len(client.sent) == 1


def test_an_image_becomes_a_text_then_image_url_list() -> None:
    client = _FakeClient([])
    llm.generate_json(
        KEYS, "system", "user text", OkSchema,
        client_factory=_factory(client), image=IMAGE,
    )
    content = _user_content(client)
    assert content == [
        {"type": "text", "text": "user text"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{B64}"}},
    ]


def test_the_system_message_is_untouched_by_an_image() -> None:
    client = _FakeClient([])
    llm.generate_json(
        KEYS, "system", "user", OkSchema, client_factory=_factory(client), image=IMAGE
    )
    assert client.sent[0][0]["role"] == "system"
    assert isinstance(client.sent[0][0]["content"], str)


@pytest.mark.parametrize(
    "status,message",
    [
        (400, "This model does not support image input"),
        (404, "No vision model found for this endpoint"),
        (422, "multimodal content is not accepted here"),
        (400, "unsupported content type in messages"),
        (400, "image_url is not a valid message part"),
    ],
)
def test_a_model_that_cannot_read_images_retries_without_it(status, message) -> None:
    client = _FakeClient([_status_error(status, message)])
    result, _, notes = llm.generate_json(
        KEYS, "system", "user text", OkSchema,
        client_factory=_factory(client), image=IMAGE,
    )
    assert result.ok is True
    assert len(client.sent) == 2
    assert isinstance(_user_content(client, 0), list)
    assert _user_content(client, 1) == "user text"
    assert notes == [
        "Key 1 (Gemini, test-model) can't read images — the screenshot was not used.",
        "Used Key 1 (Gemini, test-model)",
    ]


def test_another_400_does_not_retry_without_the_image() -> None:
    client = _FakeClient([_status_error(400, "your prompt is far too long")])
    with pytest.raises(llm.ProviderError):
        llm.generate_json(
            KEYS, "system", "user", OkSchema,
            client_factory=_factory(client), image=IMAGE,
        )
    assert len(client.sent) == 1


def test_an_image_error_without_an_image_is_not_retried() -> None:
    client = _FakeClient([_status_error(400, "this model does not support image input")])
    with pytest.raises(llm.ProviderError):
        llm.generate_json(
            KEYS, "system", "user", OkSchema, client_factory=_factory(client)
        )
    assert len(client.sent) == 1


def test_a_404_without_an_image_still_means_the_model_is_gone() -> None:
    client = _FakeClient([_status_error(404, "model has been retired")])
    with pytest.raises(llm.ModelUnavailableError):
        llm.generate_json(
            KEYS, "system", "user", OkSchema, client_factory=_factory(client)
        )


def test_json_mode_fallback_keeps_the_image() -> None:
    client = _FakeClient([_status_error(400, "response_format is not supported")])
    llm.generate_json(
        KEYS, "system", "user text", OkSchema,
        client_factory=_factory(client), image=IMAGE,
    )
    assert len(client.sent) == 2
    assert isinstance(_user_content(client, 1), list)


def test_the_image_data_never_reaches_the_logs(caplog) -> None:
    client = _FakeClient([_status_error(400, "this model does not support image input")])
    with caplog.at_level(logging.DEBUG, logger="qagenius.llm"):
        llm.generate_json(
            KEYS, "system", "user", OkSchema,
            client_factory=_factory(client), image=IMAGE,
        )
    assert B64 not in caplog.text
    assert "image attached: yes" in caplog.text
    assert str(len(B64)) not in caplog.text


def test_a_call_without_an_image_says_so_in_the_log(caplog) -> None:
    client = _FakeClient([])
    with caplog.at_level(logging.DEBUG, logger="qagenius.llm"):
        llm.generate_json(KEYS, "system", "user", OkSchema, client_factory=_factory(client))
    assert "image attached: no" in caplog.text
