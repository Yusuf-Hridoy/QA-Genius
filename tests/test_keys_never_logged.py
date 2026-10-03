"""The key value must never appear in logs or responses. No network."""

import json
import logging

import httpx
import openai
from fastapi.testclient import TestClient
from pydantic import BaseModel

import main
from qagenius import llm

SECRET = "sk-TESTSECRET123"


class OkSchema(BaseModel):
    ok: bool


def _rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    return openai.RateLimitError(
        "rate limited",
        response=httpx.Response(429, request=request),
        body=None,
    )


class _FailingClient:
    def __init__(self) -> None:
        class Completions:
            def create(self, **kwargs):
                raise _rate_limit_error()

        self.chat = type("Chat", (), {"completions": Completions()})()


class _PassingClient:
    def __init__(self) -> None:
        message = type("Message", (), {"content": '{"ok": true}'})()
        choice = type("Choice", (), {"message": message})()
        completion = type("Completion", (), {"choices": [choice]})()

        class Completions:
            def create(self, **kwargs):
                return completion

        self.chat = type("Chat", (), {"completions": Completions()})()


def _failing_factory(base_url: str, api_key: str):
    return _FailingClient()


def _passing_factory(base_url: str, api_key: str):
    return _PassingClient()


def test_failing_and_passing_calls_never_log_key(caplog) -> None:
    keys = [{"provider": "gemini", "key": SECRET, "label": "mine"}]
    with caplog.at_level(logging.WARNING, logger="qagenius.llm"):
        try:
            llm.generate_json(
                keys, "system", "user", OkSchema, client_factory=_failing_factory
            )
        except llm.AllKeysBusyError as e:
            assert SECRET not in str(e)
            assert SECRET not in " ".join(e.notes)
        result, _, notes = llm.generate_json(
            keys, "system", "user", OkSchema, client_factory=_passing_factory
        )
        assert result.ok is True
        assert SECRET not in " ".join(notes)
    assert SECRET not in caplog.text


def test_key_test_endpoint_never_echoes_key() -> None:
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post(
        "/api/keys/test", json={"provider": "unknown-provider", "key": SECRET}
    )
    assert response.json() == {
        "ok": False,
        "error": "Pick a provider and paste a key.",
    }
    assert SECRET not in response.text


def test_story_run_error_never_echoes_key(monkeypatch) -> None:
    def fake(keys, system, user, schema):
        raise llm.AllKeysBusyError(["Key 1 (Gemini) was busy, trying the next key"])

    monkeypatch.setattr(llm, "generate_json", fake)
    client = TestClient(main.app, raise_server_exceptions=False)
    header = {
        "X-QAG-Keys": json.dumps([{"provider": "gemini", "key": SECRET}])
    }
    response = client.post(
        "/requirements/story/run",
        data={"user_story": "As a shopper, I want X."},
        headers=header,
    )
    assert SECRET not in response.text
