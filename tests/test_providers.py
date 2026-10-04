from qagenius.providers import PROVIDERS, get_provider, pick_default

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
        for field in ("id", "name", "base_url", "key_url"):
            value = provider.get(field, "")
            assert isinstance(value, str) and value.strip(), (provider.get("id"), field)
        preferred = provider.get("preferred", [])
        assert isinstance(preferred, list) and preferred, provider.get("id")
        assert all(
            isinstance(fragment, str) and fragment.strip() for fragment in preferred
        ), provider.get("id")
        assert provider["base_url"].startswith("https://"), provider["id"]
        assert provider["key_url"].startswith("https://"), provider["id"]


def test_pick_default_respects_fragment_order() -> None:
    groq = get_provider("groq")
    assert groq is not None
    ids = ["qwen/qwen3-32b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
    assert pick_default(groq, ids) == "llama-3.3-70b-versatile"


def test_pick_default_falls_back_to_first_id() -> None:
    openai_provider = get_provider("openai")
    assert openai_provider is not None
    assert pick_default(openai_provider, ["zzz-1", "aaa-2"]) == "zzz-1"
    assert pick_default(openai_provider, []) == ""


def test_pick_default_free_fragment() -> None:
    openrouter = get_provider("openrouter")
    assert openrouter is not None
    ids = ["google/gemini-3.8-flash", "meta/llama-free-model:free", "openai/gpt-1"]
    assert pick_default(openrouter, ids) == "meta/llama-free-model:free"
