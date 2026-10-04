"""Check one provider key with a tiny JSON request. The key is never printed."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

import openai

from qagenius import llm
from qagenius.providers import get_provider, pick_default


class Ok(BaseModel):
    ok: bool


def main() -> int:
    provider_id = input("Provider id (e.g. gemini, groq, openai): ").strip()
    provider = get_provider(provider_id)
    if provider is None:
        print(f"Unknown provider id: {provider_id}")
        return 2
    key = getpass.getpass("API key (hidden while typing): ").strip()
    if not key:
        print("No key entered.")
        return 2
    try:
        models = llm.list_chat_models(provider, key)
    except openai.OpenAIError as e:
        print(f"FAILED: {llm.clean_reason(str(e), key)}")
        return 1
    except Exception:
        print("FAILED: Could not list models. Try again.")
        return 1
    model = pick_default(provider, models)
    if not model:
        print("FAILED: No chat models found for this key.")
        return 1
    try:
        llm.generate_json(
            [{"provider": provider_id, "key": key, "label": "check", "model": model}],
            'Reply with exactly {"ok": true}.',
            'Reply with exactly {"ok": true}.',
            Ok,
        )
    except (
        llm.NoKeysError,
        llm.AllKeysBusyError,
        llm.InvalidKeyError,
        llm.ModelUnavailableError,
        llm.ProviderError,
        llm.BadOutputError,
    ) as e:
        print(f"FAILED: {e}")
        for note in getattr(e, "notes", []):
            print(f"  - {note}")
        return 1
    print(f"OK {provider_id} {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
