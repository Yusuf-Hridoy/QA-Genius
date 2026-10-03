"""Check one provider key with a tiny JSON request. The key is never printed."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

from qagenius import llm
from qagenius.providers import get_provider


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
        llm.generate_json(
            [{"provider": provider_id, "key": key, "label": "check"}],
            'Reply with exactly {"ok": true}.',
            'Reply with exactly {"ok": true}.',
            Ok,
        )
    except (
        llm.NoKeysError,
        llm.AllKeysBusyError,
        llm.InvalidKeyError,
        llm.ProviderError,
        llm.BadOutputError,
    ) as e:
        print(f"FAILED: {e}")
        return 1
    print(f"OK {provider_id} {provider['model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
