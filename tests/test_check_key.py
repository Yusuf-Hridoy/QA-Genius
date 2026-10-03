"""scripts/check_key.py prints notes on failure and never the key."""

import getpass

from scripts import check_key
from qagenius import llm


def test_check_key_prints_notes_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "gemini")
    monkeypatch.setattr(getpass, "getpass", lambda _: "my-hidden-key")

    def fake(*args, **kwargs):
        raise llm.ModelUnavailableError(
            ['Key 1 (Gemini): the model "gemini-x" is not available']
        )

    monkeypatch.setattr(check_key.llm, "generate_json", fake)
    assert check_key.main() == 1
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "not available" in out
    assert "my-hidden-key" not in out
