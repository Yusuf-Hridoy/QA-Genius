"""Provider table: every provider is called with the `openai` client via its base_url.

`preferred` lists name fragments (not exact ids) used to pick a default
model from a provider's live /models list. Models retire often; the live
list is the source of truth.
"""

PROVIDERS: list[dict] = [
    {
        "id": "gemini",
        "name": "Google Gemini (free)",
        "short": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "preferred": ["flash"],
        "key_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "groq",
        "name": "Groq (free)",
        "short": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "preferred": ["llama", "gpt-oss", "qwen"],
        "key_url": "https://console.groq.com/keys",
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "short": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "preferred": ["mini", "gpt"],
        "key_url": "https://platform.openai.com/api-keys",
    },
    {
        "id": "xai",
        "name": "xAI (Grok)",
        "short": "Grok",
        "base_url": "https://api.x.ai/v1",
        "preferred": ["grok"],
        "key_url": "https://console.x.ai",
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "short": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "preferred": ["small", "medium"],
        "key_url": "https://console.mistral.ai/api-keys",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "short": "Claude",
        "base_url": "https://api.anthropic.com/v1/",
        "preferred": ["haiku", "sonnet"],
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "short": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "preferred": [":free"],
        "key_url": "https://openrouter.ai/keys",
    },
]

BY_ID: dict[str, dict] = {p["id"]: p for p in PROVIDERS}


def get_provider(provider_id: str) -> dict | None:
    return BY_ID.get(provider_id)


def pick_default(provider: dict, model_ids: list[str]) -> str:
    """Pick a default model id: first fragment hit wins, ids newest-first."""
    ordered = sorted(model_ids, reverse=True)
    for fragment in provider.get("preferred", []):
        needle = str(fragment).lower()
        for model_id in ordered:
            if needle in model_id.lower():
                return model_id
    return ordered[0] if ordered else ""
