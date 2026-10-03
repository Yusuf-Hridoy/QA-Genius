from qagenius.providers import PROVIDERS

EXPECTED_IDS = {
    "gemini",
    "groq",
    "openai",
    "xai",
    "mistral",
    "anthropic",
    "openrouter",
}


def test_every_provider_has_required_fields() -> None:
    assert {p["id"] for p in PROVIDERS} == EXPECTED_IDS
    for provider in PROVIDERS:
        for field in ("id", "name", "base_url", "model", "key_url"):
            value = provider.get(field, "")
            assert isinstance(value, str) and value.strip(), (provider.get("id"), field)
        assert provider["base_url"].startswith("https://"), provider["id"]
        assert provider["key_url"].startswith("https://"), provider["id"]
