"""POST /api/keys/models. No network (the id fetcher is faked)."""

import httpx
import openai
from fastapi.testclient import TestClient

import main
from qagenius import llm

client = TestClient(main.app, raise_server_exceptions=False)

SECRET = "sk-TESTSECRET123456789012"


def test_models_are_filtered_sorted_and_suggested(monkeypatch) -> None:
    def fake_fetch(base_url: str, api_key: str):
        assert api_key == "k"
        return [
            "whisper-large-v3",
            "llama-3.3-70b-versatile",
            "llama-guard-4-12b",
            "llama-3.1-8b-instant",
        ]

    monkeypatch.setattr(llm, "fetch_model_ids", fake_fetch)
    response = client.post(
        "/api/keys/models", json={"provider": "groq", "key": "k"}
    )
    assert response.json() == {
        "ok": True,
        "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
        "suggested": "llama-3.3-70b-versatile",
    }


def test_gemini_prefix_is_stripped(monkeypatch) -> None:
    def fake_fetch(base_url: str, api_key: str):
        return ["models/gemini-3.8-flash", "models/gemini-audio-x"]

    monkeypatch.setattr(llm, "fetch_model_ids", fake_fetch)
    response = client.post(
        "/api/keys/models", json={"provider": "gemini", "key": "k"}
    )
    assert response.json() == {
        "ok": True,
        "models": ["gemini-3.8-flash"],
        "suggested": "gemini-3.8-flash",
    }


def test_models_error_is_cleaned_and_keyless(monkeypatch, caplog) -> None:
    import logging

    def fake_fetch(base_url: str, api_key: str):
        request = httpx.Request("POST", base_url + "/chat/completions")
        raise openai.BadRequestError(
            f"Invalid argument for key {SECRET}: rejected",
            response=httpx.Response(400, request=request),
            body=None,
        )

    monkeypatch.setattr(llm, "fetch_model_ids", fake_fetch)
    with caplog.at_level(logging.WARNING, logger="qagenius.web"):
        response = client.post(
            "/api/keys/models", json={"provider": "groq", "key": SECRET}
        )
    body = response.json()
    assert body["ok"] is False
    assert SECRET not in response.text
    assert SECRET not in caplog.text


def test_models_unknown_provider() -> None:
    response = client.post(
        "/api/keys/models", json={"provider": "nope", "key": "x"}
    )
    assert response.json() == {
        "ok": False,
        "error": "Pick a provider and paste a key.",
    }
