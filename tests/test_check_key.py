"""scripts/check_key.py prints notes on failure and never the key."""

import getpass

from pydantic import BaseModel

from scripts import check_key
from qagenius import llm


def test_check_key_prints_notes_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "gemini")
    monkeypatch.setattr(getpass, "getpass", lambda _: "my-hidden-key")
    monkeypatch.setattr(
        check_key.llm, "list_chat_models", lambda provider, key: ["picked-model"]
    )

    def fake(*args, **kwargs):
        assert kwargs.get("model", None) is None
        raise llm.ModelUnavailableError(
            ['Key 1 (Gemini): the model "gemini-x" is not available']
        )

    monkeypatch.setattr(check_key.llm, "generate_json", fake)
    assert check_key.main() == 1
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "not available" in out
    assert "my-hidden-key" not in out


def test_check_key_ok_names_resolved_model(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "groq")
    monkeypatch.setattr(getpass, "getpass", lambda _: "my-hidden-key")
    monkeypatch.setattr(
        check_key.llm, "list_chat_models", lambda provider, key: ["zzz-model"]
    )
    seen: dict = {}

    def fake(keys, system, user, schema):
        seen["model"] = keys[0].get("model")

        class Ok(BaseModel):
            ok: bool

        return Ok(ok=True), 0, []

    monkeypatch.setattr(check_key.llm, "generate_json", fake)
    assert check_key.main() == 0
    out = capsys.readouterr().out
    assert seen["model"] == "zzz-model"
    assert "OK groq zzz-model" in out
    assert "my-hidden-key" not in out
